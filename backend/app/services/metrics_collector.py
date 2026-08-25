import asyncio
import logging
from datetime import (
    datetime,
    timezone,
)

from app.core.collections import (
    METRICS_COLLECTION_NAME,
)
from app.core.config import settings
from app.services.database_overview import (
    collect_database_overview,
)
from app.services.database_connections import monitored_connections_filter


logger = logging.getLogger(__name__)


COLLECTOR_CONCURRENCY = 5


def build_metric_sample(
    overview: dict,
) -> dict:
    return {
        "meta": {
            "connection_id":
                overview["connection_id"],

            "engine":
                overview["engine"],
        },

        "collected_at":
            datetime.now(timezone.utc),

        "checked_at":
            overview.get("checked_at"),

        "status":
            overview.get(
                "status",
                "unreachable",
            ),

        "response_time_ms":
            overview.get(
                "response_time_ms"
            ),

        "active":
            overview.get("active"),

        "connections":
            overview.get("connections"),

        "blocked":
            overview.get("blocked"),

        "uptime_seconds":
            overview.get(
                "uptime_seconds"
            ),

        "warnings":
            overview.get(
                "warnings",
                [],
            ),

        "error":
            overview.get("error"),
    }


async def collect_metrics_once(
    database,
) -> int:
    cursor = (
        database.database_connections
        .find(
            monitored_connections_filter()
        )
        .sort(
            "name",
            1,
        )
    )

    connections = await cursor.to_list(
        None
    )

    if not connections:
        logger.info(
            "Metrics collection skipped "
            "reason=no_monitored_connections"
        )

        return 0

    semaphore = asyncio.Semaphore(
        COLLECTOR_CONCURRENCY
    )

    async def collect_one(
        connection: dict,
    ):
        try:
            async with semaphore:
                overview = (
                    await collect_database_overview(
                        connection
                    )
                )

            return build_metric_sample(
                overview
            )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Metric collection failed "
                "connection_id=%s "
                "engine=%s",
                str(
                    connection.get(
                        "_id",
                        "unknown",
                    )
                ),
                connection.get(
                    "engine",
                    "unknown",
                ),
            )

            return None

    results = await asyncio.gather(
        *[
            collect_one(connection)
            for connection in connections
        ]
    )

    samples = [
        result
        for result in results
        if result is not None
    ]

    if not samples:
        logger.warning(
            "Metrics collection completed "
            "samples=0 connections=%s",
            len(connections),
        )

        return 0

    collection = database[
        METRICS_COLLECTION_NAME
    ]

    result = await collection.insert_many(
        samples
    )

    inserted_count = len(
        result.inserted_ids
    )

    logger.info(
        "Metrics collection completed "
        "samples=%s connections=%s",
        inserted_count,
        len(connections),
    )

    return inserted_count


async def run_metrics_collector(
    database,
) -> None:
    interval = max(
        settings
        .metrics_collector_interval_seconds,
        5,
    )

    logger.info(
        "Metrics collector started "
        "interval_seconds=%s",
        interval,
    )

    while True:
        try:
            await collect_metrics_once(
                database
            )

        except asyncio.CancelledError:
            logger.info(
                "Metrics collector stopped"
            )
            raise

        except Exception:
            logger.exception(
                "Metrics collector cycle failed"
            )

        await asyncio.sleep(
            interval
        )