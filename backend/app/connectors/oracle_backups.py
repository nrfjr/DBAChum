from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.core.exceptions import AppError


BACKUP_HISTORY_LIMIT = 500


def _oracle_backup_kind(input_type: str | None) -> str:
    value = (input_type or "").strip().upper()
    if value in {"DB FULL", "DATAFILE FULL"}:
        return "full"
    if value in {"DB INCR", "DATAFILE INCR"}:
        return "incremental"
    if value == "ARCHIVELOG":
        return "archive_log"
    if value == "CONTROLFILE":
        return "controlfile"
    if value == "SPFILE":
        return "spfile"
    return "other"


def _oracle_backup_status(status: str | None) -> str:
    value = (status or "").strip().upper()
    if value == "COMPLETED":
        return "successful"
    if "WARNING" in value or "ERROR" in value:
        return "warning"
    if value == "FAILED":
        return "failed"
    if value.startswith("RUNNING"):
        return "running"
    return "unknown"


def _plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _window_clause(history_filter: dict) -> tuple[str, dict]:
    window = history_filter.get("window", "today")
    timestamp = "NVL(end_time, start_time)"

    if window == "today":
        return (
            f"{timestamp} >= TRUNC(SYSDATE) AND {timestamp} < TRUNC(SYSDATE) + 1",
            {},
        )

    if window in {"3d", "7d"}:
        days = 3 if window == "3d" else 7
        return (
            f"{timestamp} >= TRUNC(SYSDATE) - {days - 1} "
            f"AND {timestamp} < TRUNC(SYSDATE) + 1",
            {},
        )

    start_date = history_filter["start_date"]
    end_date = history_filter["end_date"]
    return (
        f"{timestamp} >= :start_date AND {timestamp} < :end_date",
        {
            "start_date": datetime.combine(start_date, time.min),
            "end_date": datetime.combine(end_date + timedelta(days=1), time.min),
        },
    )


def _select_sql(
    where_clause: str | None,
    row_limit: int,
    *,
    detailed: bool = True,
) -> str:
    where_sql = f"WHERE {where_clause}" if where_clause else ""
    detail_columns = ""
    if detailed:
        detail_columns = """,
                optimized,
                compression_ratio,
                input_bytes_per_sec,
                output_bytes_per_sec,
                input_bytes_display,
                output_bytes_display,
                input_bytes_per_sec_display,
                output_bytes_per_sec_display,
                time_taken_display"""

    return f"""
        SELECT * FROM (
            SELECT
                session_key,
                input_type,
                status,
                start_time,
                end_time,
                elapsed_seconds,
                input_bytes,
                output_bytes,
                output_device_type
                {detail_columns}
            FROM v$rman_backup_job_details
            {where_sql}
            ORDER BY NVL(end_time, start_time) DESC, session_key DESC
        )
        WHERE ROWNUM <= {row_limit}
    """


def _backup_item(row, database_name: str | None) -> dict:
    native_status = str(row[2]).strip() if row[2] is not None else None
    details = {
        "rman_session_key": _plain(row[0]),
    }
    if len(row) > 9:
        details.update(
            {
                "optimized": _plain(row[9]),
                "compression_ratio": _plain(row[10]),
                "input_bytes_per_second": _plain(row[11]),
                "output_bytes_per_second": _plain(row[12]),
                "input_size_display": _plain(row[13]),
                "output_size_display": _plain(row[14]),
                "input_rate_display": _plain(row[15]),
                "output_rate_display": _plain(row[16]),
                "time_taken_display": _plain(row[17]),
            }
        )
    details = {key: value for key, value in details.items() if value is not None}

    return {
        "backup_id": str(row[0]),
        "database_name": database_name,
        "kind": _oracle_backup_kind(row[1]),
        "native_type": row[1],
        "status": _oracle_backup_status(native_status),
        "native_status": native_status,
        "started_at": row[3],
        "finished_at": row[4],
        "duration_seconds": int(row[5]) if row[5] is not None else None,
        "input_bytes": int(row[6]) if row[6] is not None else None,
        "output_bytes": int(row[7]) if row[7] is not None else None,
        "backup_size_bytes": int(row[7]) if row[7] is not None else None,
        "destinations": [],
        "device_type": row[8],
        "label": None,
        "owner": None,
        "details": details,
    }


def _latest(items: list[dict], *kinds: str) -> dict | None:
    for item in items:
        if item["kind"] in kinds and item["status"] in {"successful", "warning"}:
            return item
    return None


async def get_oracle_backups(connection: dict, history_filter: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        async with open_oracle_connection(connection) as db:
            database_row = await db.fetchone(
                "SELECT name, log_mode FROM v$database"
            )
            database_name = database_row[0] if database_row else None

            where_clause, parameters = _window_clause(history_filter)

            try:
                try:
                    rows = await db.fetchall(
                        _select_sql(where_clause, BACKUP_HISTORY_LIMIT + 1),
                        parameters or None,
                    )
                    latest_rows = await db.fetchall(_select_sql(None, 1))
                except oracledb.Error:
                    rows = await db.fetchall(
                        _select_sql(
                            where_clause,
                            BACKUP_HISTORY_LIMIT + 1,
                            detailed=False,
                        ),
                        parameters or None,
                    )
                    latest_rows = await db.fetchall(
                        _select_sql(None, 1, detailed=False)
                    )
                    warnings.append(
                        "Core RMAN backup history is available, but this Oracle version "
                        "does not expose all extended job-detail columns."
                    )
            except oracledb.Error as exc:
                return {
                    "available": False,
                    "source": "Oracle RMAN control-file history",
                    "scope": "database",
                    "database_name": database_name,
                    "generation": db.version,
                    "latest_backup": None,
                    "summaries": [],
                    "items": [],
                    "truncated": False,
                    "warnings": [
                        "RMAN backup history is unavailable to this account: "
                        f"{oracle_error_message(exc)}"
                    ],
                    "notes": [],
                    "checked_at": checked_at,
                }

            truncated = len(rows) > BACKUP_HISTORY_LIMIT
            rows = rows[:BACKUP_HISTORY_LIMIT]
            items = [_backup_item(row, database_name) for row in rows]
            latest_backup = (
                _backup_item(latest_rows[0], database_name)
                if latest_rows
                else None
            )

            summary_name = database_name or "Oracle database"
            summaries = [
                {
                    "database_name": summary_name,
                    "recovery_model": database_row[1] if database_row else None,
                    "last_full": _latest(items, "full"),
                    "last_differential": None,
                    "last_incremental": _latest(items, "incremental"),
                    "last_log": _latest(items, "archive_log"),
                }
            ]

            if not rows:
                warnings.append(
                    "No RMAN backup jobs were recorded in the selected range."
                )

            notes: list[str] = []
            if truncated:
                notes.append(
                    f"The selected range returned more than {BACKUP_HISTORY_LIMIT} RMAN jobs; "
                    "only the newest records are shown. Narrow the custom date range for the full list."
                )

            return {
                "available": True,
                "source": "Oracle RMAN control-file history",
                "scope": "database",
                "database_name": database_name,
                "generation": db.version,
                "latest_backup": latest_backup,
                "summaries": summaries,
                "items": items,
                "truncated": truncated,
                "warnings": warnings,
                "notes": notes,
                "checked_at": checked_at,
            }

    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_BACKUP_MONITORING_FAILED",
            status_code=400,
        ) from exc
