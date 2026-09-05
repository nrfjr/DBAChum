import asyncio
import logging
import time

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
    sqlserver_error_message,
)
from app.core.exceptions import AppError


logger = logging.getLogger(__name__)


def _test_sqlserver_sync(connection: dict) -> dict:
    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)

            return {
                "database_name": identity.database_name,
                "connected_user": identity.connected_user,
                "database_version": identity.version.raw,
                "service_name": None,
                "database_edition": identity.edition,
                "sqlserver_generation": identity.version.generation,
                "sqlserver_provider": identity.provider,
                "sqlserver_driver": identity.driver,
                "capabilities": identity.capabilities,
            }
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_CONNECTION_FAILED",
            status_code=400,
        ) from exc


async def test_sqlserver_connection(connection: dict) -> dict:
    return await asyncio.to_thread(_test_sqlserver_sync, connection)


def _sqlserver_scalar(
    cursor,
    sql: str,
    metric_name: str,
    warnings: list[str],
):
    try:
        cursor.execute(sql)
        row = cursor.fetchone()
        return None if row is None else row[0]
    except Exception as exc:
        logger.warning(
            "SQL Server overview metric '%s' unavailable: %s",
            metric_name,
            exc,
        )
        warnings.append(f"{metric_name} unavailable.")
        return None


def _get_sqlserver_overview_sync(connection: dict) -> dict:
    try:
        with open_sqlserver_connection(connection) as db:
            warnings: list[str] = []
            cursor = db.cursor()
            try:
                started = time.perf_counter()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                response_time_ms = round(
                    (time.perf_counter() - started) * 1000,
                    1,
                )

                identity = probe_sqlserver_identity(db)

                cursor.execute(
                    """
                    SELECT
                        SUM(CASE
                            WHEN spid <> @@SPID
                             AND spid > 50
                             AND status NOT IN ('sleeping', 'background', 'dormant')
                            THEN 1 ELSE 0 END),
                        SUM(CASE
                            WHEN spid <> @@SPID
                             AND spid > 50
                            THEN 1 ELSE 0 END),
                        SUM(CASE
                            WHEN spid <> @@SPID
                             AND spid > 50
                             AND blocked <> 0
                            THEN 1 ELSE 0 END)
                    FROM master.dbo.sysprocesses
                    """
                )
                counts = cursor.fetchone()

                uptime_seconds = _sqlserver_scalar(
                    cursor,
                    """
                    SELECT DATEDIFF(SECOND, crdate, GETDATE())
                    FROM master.dbo.sysdatabases
                    WHERE name = 'tempdb'
                    """,
                    "Uptime",
                    warnings,
                )

                return {
                    "response_time_ms": response_time_ms,
                    "active": int(counts[0] or 0) if counts else None,
                    "connections": int(counts[1] or 0) if counts else None,
                    "blocked": int(counts[2] or 0) if counts else None,
                    "uptime_seconds": (
                        int(uptime_seconds)
                        if uptime_seconds is not None
                        else None
                    ),
                    "database_name": identity.database_name,
                    "container_name": None,
                    "service_name": None,
                    "instance_name": identity.instance_name,
                    "version": identity.version.raw,
                    "edition": identity.edition,
                    "product_level": identity.product_level,
                    "generation": identity.version.generation,
                    "connection_provider": identity.provider,
                    "connection_driver": identity.driver,
                    "connection_encrypt": identity.encrypt,
                    "capabilities": identity.capabilities,
                    "warnings": warnings,
                }
            finally:
                cursor.close()

    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_MONITORING_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_overview(connection: dict) -> dict:
    return await asyncio.to_thread(_get_sqlserver_overview_sync, connection)
