from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.core.exceptions import AppError


BACKUP_HISTORY_LIMIT = 100


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


def _latest(items: list[dict], *kinds: str) -> dict | None:
    for item in items:
        if item["kind"] in kinds and item["status"] in {"successful", "warning"}:
            return item
    return None


async def get_oracle_backups(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        async with open_oracle_connection(connection) as db:
            database_row = await db.fetchone(
                "SELECT name, log_mode FROM v$database"
            )

            try:
                rows = await db.fetchall(
                    f"""
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
                        FROM v$rman_backup_job_details
                        ORDER BY start_time DESC
                    )
                    WHERE ROWNUM <= {BACKUP_HISTORY_LIMIT}
                    """
                )
            except oracledb.Error as exc:
                return {
                    "available": False,
                    "source": "Oracle RMAN control-file history",
                    "scope": "database",
                    "database_name": database_row[0] if database_row else None,
                    "generation": db.version,
                    "summaries": [],
                    "items": [],
                    "warnings": [
                        "RMAN backup history is unavailable to this account: "
                        f"{oracle_error_message(exc)}"
                    ],
                    "notes": [],
                    "checked_at": checked_at,
                }

            items = []
            for row in rows:
                items.append(
                    {
                        "backup_id": str(row[0]),
                        "database_name": database_row[0] if database_row else None,
                        "kind": _oracle_backup_kind(row[1]),
                        "native_type": row[1],
                        "status": _oracle_backup_status(row[2]),
                        "started_at": row[3],
                        "finished_at": row[4],
                        "duration_seconds": int(row[5]) if row[5] is not None else None,
                        "input_bytes": int(row[6]) if row[6] is not None else None,
                        "output_bytes": int(row[7]) if row[7] is not None else None,
                        "backup_size_bytes": int(row[7]) if row[7] is not None else None,
                        "destinations": [],
                        "device_type": row[8],
                    }
                )

            database_name = database_row[0] if database_row else "Oracle database"
            summaries = [
                {
                    "database_name": database_name,
                    "recovery_model": database_row[1] if database_row else None,
                    "last_full": _latest(items, "full"),
                    "last_differential": None,
                    "last_incremental": _latest(items, "incremental"),
                    "last_log": _latest(items, "archive_log"),
                }
            ]

            if not rows:
                warnings.append("No RMAN backup jobs are visible in control-file history.")

            return {
                "available": True,
                "source": "Oracle RMAN control-file history",
                "scope": "database",
                "database_name": database_row[0] if database_row else None,
                "generation": db.version,
                "summaries": summaries,
                "items": items,
                "warnings": warnings,
                "notes": [],
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
