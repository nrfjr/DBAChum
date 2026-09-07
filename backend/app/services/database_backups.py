from datetime import date, datetime, time, timedelta, timezone

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


def _history_datetime_bounds(history_filter: dict) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    window = history_filter["window"]
    if window == "custom":
        start_date = history_filter["start_date"]
        end_date = history_filter["end_date"]
        return (
            datetime.combine(start_date, time.min, tzinfo=timezone.utc),
            datetime.combine(end_date, time.max, tzinfo=timezone.utc),
        )

    days = {"today": 1, "3d": 3, "7d": 7}[window]
    start_day = now.date() - timedelta(days=days - 1)
    return (
        datetime.combine(start_day, time.min, tzinfo=timezone.utc),
        now,
    )


def _audit_backup_kind(action: str) -> str:
    suffix = action.removeprefix("backup.")
    return {
        "full": "full",
        "differential": "differential",
        "log": "log",
        "archivelog": "archive_log",
        "database_plus_archivelog": "full",
    }.get(suffix, "other")


def _audit_backup_status(status: str) -> str:
    return {
        "succeeded": "successful",
        "failed": "failed",
        "running": "running",
    }.get(status, "unknown")


async def _load_dbachum_backup_actions(
    database,
    connection_id: str,
    history_filter: dict,
    *,
    limit: int = 250,
) -> list[dict]:
    start_at, end_at = _history_datetime_bounds(history_filter)
    cursor = (
        database.database_action_audit
        .find(
            {
                "connection_id": connection_id,
                "action": {"$regex": r"^backup\."},
                "started_at": {"$gte": start_at, "$lte": end_at},
            }
        )
        .sort("started_at", -1)
        .limit(limit)
    )
    documents = await cursor.to_list(length=limit)
    items: list[dict] = []
    for document in documents:
        started_at = document.get("started_at")
        completed_at = document.get("completed_at")
        duration = None
        if started_at and completed_at:
            duration = max(int((completed_at - started_at).total_seconds()), 0)
        details = document.get("details") or {}
        destination = details.get("destination")
        safe_details = {
            key: value
            for key, value in {
                "server_name": details.get("server_name"),
                "exit_status": details.get("exit_status"),
                "statement_executed": details.get("statement_executed"),
            }.items()
            if value is not None
        }
        items.append(
            {
                "backup_id": f"dbachum:{document['_id']}",
                "database_name": document.get("target"),
                "kind": _audit_backup_kind(document.get("action", "")),
                "native_type": "DBAChum " + document.get("action", "backup").removeprefix("backup.").replace("_", " "),
                "status": _audit_backup_status(document.get("status", "unknown")),
                "native_status": document.get("status"),
                "started_at": started_at,
                "finished_at": completed_at,
                "duration_seconds": duration,
                "destinations": [str(destination)] if destination else [],
                "device_type": "SSH/mysqldump" if document.get("engine") == "mysql" else "DBAChum",
                "label": "DBAChum executed backup",
                "owner": document.get("operator_username"),
                "details": safe_details,
            }
        )
    return items


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
        executed_items = await _load_dbachum_backup_actions(
            database, connection_id, history_filter
        )
        if executed_items:
            result = {
                **result,
                "available": True,
                "source": "DBAChum executed mysqldump jobs",
                "latest_backup": executed_items[0],
                "items": executed_items,
                "notes": [
                    "MySQL/MariaDB has no universal native backup-history repository. "
                    "This view lists logical backups executed by DBAChum; external provider history can be integrated separately."
                ],
            }
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
