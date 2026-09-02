import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
    sqlserver_error_message,
)
from app.core.exceptions import AppError


BACKUP_HISTORY_LIMIT = 250

_SQLSERVER_BACKUP_KIND = {
    "D": "full",
    "I": "differential",
    "L": "log",
    "F": "file",
    "G": "file",
    "P": "partial",
    "Q": "partial",
}


def _backup_item(row, destinations: dict[int, list[str]]) -> dict:
    backup_set_id = int(row[0])
    media_set_id = int(row[1]) if row[1] is not None else None
    started_at = row[4]
    finished_at = row[5]

    duration_seconds = None
    if started_at is not None and finished_at is not None:
        try:
            duration_seconds = max(
                int((finished_at - started_at).total_seconds()),
                0,
            )
        except Exception:
            duration_seconds = None

    native_type = str(row[3] or "").strip().upper()

    return {
        "backup_id": str(backup_set_id),
        "database_name": row[2],
        "kind": _SQLSERVER_BACKUP_KIND.get(native_type, "other"),
        "native_type": native_type or None,
        "status": "successful",
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "backup_size_bytes": int(row[6]) if row[6] is not None else None,
        "destinations": destinations.get(media_set_id, []) if media_set_id else [],
        "label": row[7],
        "owner": row[8],
    }


def _latest(items: list[dict], *kinds: str) -> dict | None:
    for item in items:
        if item["kind"] in kinds:
            return item
    return None


def _get_sqlserver_backups_sync(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            cursor = db.cursor()
            try:
                try:
                    cursor.execute(
                        """
                        SELECT
                            name,
                            CAST(DATABASEPROPERTYEX(name, 'Recovery') AS varchar(32))
                        FROM master.dbo.sysdatabases
                        WHERE name <> 'tempdb'
                        ORDER BY name
                        """
                    )
                    database_rows = cursor.fetchall()
                except Exception as exc:
                    warnings.append(
                        "Database recovery-model discovery unavailable: "
                        f"{sqlserver_error_message(exc)}"
                    )
                    database_rows = []

                try:
                    cursor.execute(
                        f"""
                        SELECT TOP {BACKUP_HISTORY_LIMIT}
                            backup_set_id,
                            media_set_id,
                            database_name,
                            type,
                            backup_start_date,
                            backup_finish_date,
                            backup_size,
                            name,
                            user_name
                        FROM msdb.dbo.backupset
                        ORDER BY backup_finish_date DESC, backup_set_id DESC
                        """
                    )
                    backup_rows = cursor.fetchall()
                except Exception as exc:
                    return {
                        "available": False,
                        "source": "msdb backup history",
                        "scope": "instance",
                        "database_name": identity.database_name,
                        "generation": identity.version.generation,
                        "summaries": [],
                        "items": [],
                        "warnings": [
                            "SQL Server backup history could not be read from msdb: "
                            f"{sqlserver_error_message(exc)}"
                        ],
                        "notes": [
                            "Grant the DBAChum monitoring login read access to the "
                            "required msdb backup-history metadata, then refresh."
                        ],
                        "checked_at": checked_at,
                    }

                media_ids = sorted(
                    {
                        int(row[1])
                        for row in backup_rows
                        if row[1] is not None
                    }
                )
                destinations: dict[int, list[str]] = defaultdict(list)

                if media_ids:
                    id_list = ",".join(str(value) for value in media_ids)
                    try:
                        cursor.execute(
                            "SELECT media_set_id, physical_device_name "
                            "FROM msdb.dbo.backupmediafamily "
                            f"WHERE media_set_id IN ({id_list}) "
                            "ORDER BY media_set_id, family_sequence_number"
                        )
                        for media_row in cursor.fetchall():
                            if media_row[1]:
                                destinations[int(media_row[0])].append(
                                    str(media_row[1])
                                )
                    except Exception as exc:
                        warnings.append(
                            "Backup destination history unavailable: "
                            f"{sqlserver_error_message(exc)}"
                        )
            finally:
                cursor.close()

            items = [_backup_item(row, destinations) for row in backup_rows]
            by_database: dict[str, list[dict]] = defaultdict(list)
            for item in items:
                if item["database_name"]:
                    by_database[str(item["database_name"])].append(item)

            database_models = {
                str(row[0]): (str(row[1]) if row[1] is not None else None)
                for row in database_rows
            }
            all_names = sorted(set(database_models) | set(by_database))

            summaries = []
            for database_name in all_names:
                history = by_database.get(database_name, [])
                summaries.append(
                    {
                        "database_name": database_name,
                        "recovery_model": database_models.get(database_name),
                        "last_full": _latest(history, "full"),
                        "last_differential": _latest(history, "differential"),
                        "last_incremental": None,
                        "last_log": _latest(history, "log"),
                    }
                )

            if not backup_rows:
                warnings.append(
                    "No SQL Server backup history is visible in msdb for this instance."
                )

            # msdb backupset represents recorded backup sets. Failed attempts
            # are not a universal backupset history signal; Agent/error-log
            # correlation is intentionally a later capability.
            notes = [
                "SQL Server msdb records backup sets. Failed-attempt monitoring "
                "will be added through SQL Agent/error-log correlation."
            ]

            return {
                "available": True,
                "source": "msdb backup history",
                "scope": "instance",
                "database_name": identity.database_name,
                "generation": identity.version.generation,
                "summaries": summaries,
                "items": items,
                "warnings": warnings,
                "notes": notes,
                "checked_at": checked_at,
            }

    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_BACKUP_MONITORING_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_backups(connection: dict) -> dict:
    return await asyncio.to_thread(_get_sqlserver_backups_sync, connection)
