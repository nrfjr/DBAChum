from datetime import date

from app.connectors.mysql_backups import get_mysql_backups
from app.connectors.oracle_backups import get_oracle_backups
from app.connectors.sqlserver_backups import get_sqlserver_backups
from app.core.exceptions import AppError
from app.services.database_connections import get_database_connection


VALID_WINDOWS = {"today", "3d", "7d", "custom"}


def _backup_filter(
    window: str,
    start_date: date | None,
    end_date: date | None,
) -> dict:
    if window not in VALID_WINDOWS:
        raise AppError(
            "Unsupported backup-history range.",
            code="BACKUP_RANGE_INVALID",
            status_code=400,
        )

    if window == "custom":
        if start_date is None or end_date is None:
            raise AppError(
                "Custom backup history requires both start and end dates.",
                code="BACKUP_CUSTOM_RANGE_REQUIRED",
                status_code=400,
            )
        if end_date < start_date:
            raise AppError(
                "Custom backup history end date must be on or after the start date.",
                code="BACKUP_CUSTOM_RANGE_INVALID",
                status_code=400,
            )
    else:
        start_date = None
        end_date = None

    return {
        "window": window,
        "start_date": start_date,
        "end_date": end_date,
    }


async def load_database_backups(
    database,
    connection_id: str,
    *,
    window: str = "today",
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]
    history_filter = _backup_filter(window, start_date, end_date)

    if engine == "oracle":
        result = await get_oracle_backups(connection, history_filter)
    elif engine == "sqlserver":
        result = await get_sqlserver_backups(connection, history_filter)
    elif engine == "mysql":
        result = await get_mysql_backups(connection, history_filter)
    else:
        raise AppError(
            f"Backup monitoring is not available for {engine}.",
            code="BACKUP_MONITORING_NOT_AVAILABLE",
            status_code=400,
        )

    return {
        "connection_id": connection_id,
        "engine": engine,
        "selected_window": history_filter["window"],
        "custom_start_date": history_filter["start_date"],
        "custom_end_date": history_filter["end_date"],
        **result,
    }
