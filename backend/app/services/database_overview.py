import asyncio
import logging
from datetime import datetime, timezone

from app.connectors.mysql import get_mysql_overview
from app.connectors.oracle import get_oracle_overview
from app.connectors.sqlserver import (
    get_sqlserver_overview,
)
from app.core.exceptions import AppError
from app.services.database_connections import (
    connection_is_active,
    connection_is_monitored,
    get_database_connection,
    monitored_connections_filter,
)


logger = logging.getLogger(__name__)


def _normalize_warnings(items) -> list[str]:
    """Return stable, human-facing monitoring warnings.

    Connector fallbacks can discover the same limitation through more than one
    probe. Keep the Overview contract deterministic and avoid repeating the same
    warning in the UI while preserving the connector's original wording.
    """
    normalized: list[str] = []
    seen: set[str] = set()

    for item in items or []:
        warning = str(item).strip()
        if not warning or warning in seen:
            continue
        seen.add(warning)
        normalized.append(warning)

    return normalized


async def collect_database_overview(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    base = {
        "connection_id": str(connection["_id"]),
        "engine": connection["engine"],
        "checked_at": checked_at,
    }

    if (
        not connection_is_active(connection)
        or not connection_is_monitored(connection)
    ):
        return {
            **base,
            "status": "disabled",
            "warnings": [],
        }

    engine = connection["engine"]

    try:
        if engine == "oracle":
            result = await get_oracle_overview(
                connection
            )

        elif engine == "sqlserver":
            result = await get_sqlserver_overview(
                connection
            )

        elif engine == "mysql":
            result = await get_mysql_overview(
                connection
            )

        else:
            return {
                **base,
                "status": "unreachable",
                "warnings": [],
                "error":
                    f"Unsupported database engine: "
                    f"{engine}",
            }

    except AppError as exc:
        return {
            **base,
            "status": "unreachable",
            "warnings": [],
            "error": exc.message,
        }

    except Exception:
        logger.exception(
            "Unexpected database monitoring failure "
            "connection_id=%s engine=%s",
            base["connection_id"],
            engine,
        )

        return {
            **base,
            "status": "unreachable",
            "warnings": [],
            "error": "Monitoring failed unexpectedly.",
        }

    warnings = _normalize_warnings(result.get("warnings", []))

    return {
        **base,
        **result,
        "warnings": warnings,
        "status":
            "limited"
            if warnings
            else "online",
    }


async def get_database_overview(
    database,
    connection_id: str,
):
    connection = await get_database_connection(
        database,
        connection_id,
    )

    return await collect_database_overview(
        connection
    )


async def list_database_overviews(database):
    cursor = (
        database.database_connections
        .find(monitored_connections_filter())
        .sort("name", 1)
    )

    connections = await cursor.to_list(None)

    # Don't open fifty databases simultaneously
    # just because somebody has fifty entries.
    semaphore = asyncio.Semaphore(5)

    async def collect_with_limit(connection):
        async with semaphore:
            return await collect_database_overview(
                connection
            )

    return await asyncio.gather(
        *[
            collect_with_limit(connection)
            for connection in connections
        ]
    )