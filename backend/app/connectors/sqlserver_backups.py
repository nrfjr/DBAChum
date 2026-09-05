import asyncio
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
    sqlserver_error_message,
)
from app.core.exceptions import AppError


BACKUP_HISTORY_LIMIT = 500

_SQLSERVER_BACKUP_KIND = {
    "D": "full",
    "I": "differential",
    "L": "log",
    "F": "file",
    "G": "file",
    "P": "partial",
    "Q": "partial",
}

_DEVICE_TYPES = {
    2: "Disk",
    5: "Tape",
    7: "Virtual device",
    9: "Azure Storage",
    105: "Permanent backup device",
}


def _plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _rows_as_dicts(cursor, rows) -> list[dict]:
    columns = [str(column[0]).lower() for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def _window_clause(history_filter: dict) -> tuple[str, tuple]:
    window = history_filter.get("window", "today")

    if window == "today":
        midnight = "DATEADD(day, DATEDIFF(day, 0, GETDATE()), 0)"
        return (
            f"backup_finish_date >= {midnight} "
            f"AND backup_finish_date < DATEADD(day, 1, {midnight})",
            (),
        )

    if window in {"3d", "7d"}:
        days = 3 if window == "3d" else 7
        midnight = "DATEADD(day, DATEDIFF(day, 0, GETDATE()), 0)"
        return (
            f"backup_finish_date >= DATEADD(day, -{days - 1}, {midnight}) "
            f"AND backup_finish_date < DATEADD(day, 1, {midnight})",
            (),
        )

    start_date = history_filter["start_date"]
    end_date = history_filter["end_date"]
    start_dt = datetime.combine(start_date, time.min)
    end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min)
    return "backup_finish_date >= ? AND backup_finish_date < ?", (start_dt, end_exclusive)


def _select_columns(identity) -> list[str]:
    columns = [
        "backup_set_id",
        "media_set_id",
        "database_name",
        "type",
        "backup_start_date",
        "backup_finish_date",
        "backup_size",
        "name",
        "user_name",
    ]

    if identity.version.major is not None and identity.version.major >= 9:
        columns.extend(
            [
                "description",
                "server_name",
                "machine_name",
                "recovery_model",
                "software_major_version",
                "software_minor_version",
                "software_build_version",
                "first_lsn",
                "last_lsn",
                "checkpoint_lsn",
                "database_backup_lsn",
                "expiration_date",
                "position",
                "database_version",
                "compatibility_level",
                "collation_name",
                "is_password_protected",
            ]
        )

    if identity.capabilities.get("compression_metadata"):
        columns.extend(
            [
                "compressed_backup_size",
                "has_backup_checksums",
                "is_copy_only",
            ]
        )

    if identity.version.major is not None and identity.version.major >= 12:
        columns.extend(["key_algorithm", "encryptor_type"])

    return columns


def _fetch_backup_rows(
    cursor,
    identity,
    database_name: str,
    history_filter: dict | None,
    *,
    limit: int,
) -> tuple[list[dict], bool]:
    columns = _select_columns(identity)
    parameters: tuple = (database_name,)
    where = "database_name = ?"

    if history_filter is not None:
        range_clause, range_parameters = _window_clause(history_filter)
        where += f" AND {range_clause}"
        parameters += range_parameters

    sql = (
        f"SELECT TOP {limit} {', '.join(columns)} "
        "FROM msdb.dbo.backupset "
        f"WHERE {where} "
        "ORDER BY backup_finish_date DESC, backup_set_id DESC"
    )

    try:
        cursor.execute(sql, parameters)
        return _rows_as_dicts(cursor, cursor.fetchall()), True
    except Exception:

        base_columns = [
            "backup_set_id",
            "media_set_id",
            "database_name",
            "type",
            "backup_start_date",
            "backup_finish_date",
            "backup_size",
            "name",
            "user_name",
        ]
        fallback_sql = (
            f"SELECT TOP {limit} {', '.join(base_columns)} "
            "FROM msdb.dbo.backupset "
            f"WHERE {where} "
            "ORDER BY backup_finish_date DESC, backup_set_id DESC"
        )
        cursor.execute(fallback_sql, parameters)
        return _rows_as_dicts(cursor, cursor.fetchall()), False


def _fetch_media(cursor, media_ids: list[int]) -> tuple[dict[int, list[dict]], bool]:
    if not media_ids:
        return {}, True

    placeholders = ",".join("?" for _ in media_ids)
    parameters = tuple(media_ids)

    try:
        cursor.execute(
            "SELECT media_set_id, physical_device_name, logical_device_name, "
            "device_type, family_sequence_number "
            "FROM msdb.dbo.backupmediafamily "
            f"WHERE media_set_id IN ({placeholders}) "
            "ORDER BY media_set_id, family_sequence_number",
            parameters,
        )
        rows = _rows_as_dicts(cursor, cursor.fetchall())
        result: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            result[int(row["media_set_id"])].append(row)
        return result, True
    except Exception:
        cursor.execute(
            "SELECT media_set_id, physical_device_name "
            "FROM msdb.dbo.backupmediafamily "
            f"WHERE media_set_id IN ({placeholders}) "
            "ORDER BY media_set_id",
            parameters,
        )
        rows = _rows_as_dicts(cursor, cursor.fetchall())
        result = defaultdict(list)
        for row in rows:
            result[int(row["media_set_id"])].append(row)
        return result, False


def _backup_item(row: dict, media: dict[int, list[dict]]) -> dict:
    backup_set_id = int(row["backup_set_id"])
    media_set_id = (
        int(row["media_set_id"])
        if row.get("media_set_id") is not None
        else None
    )
    started_at = row.get("backup_start_date")
    finished_at = row.get("backup_finish_date")

    duration_seconds = None
    if started_at is not None and finished_at is not None:
        try:
            duration_seconds = max(
                int((finished_at - started_at).total_seconds()),
                0,
            )
        except Exception:
            duration_seconds = None

    native_type = str(row.get("type") or "").strip().upper()
    backup_size = int(row["backup_size"]) if row.get("backup_size") is not None else None
    compressed_size = (
        int(row["compressed_backup_size"])
        if row.get("compressed_backup_size") is not None
        else None
    )

    media_rows = media.get(media_set_id, []) if media_set_id else []
    destinations = [
        str(item["physical_device_name"])
        for item in media_rows
        if item.get("physical_device_name")
    ]
    device_labels = []
    for item in media_rows:
        device_type = item.get("device_type")
        if device_type is None:
            continue
        try:
            label = _DEVICE_TYPES.get(int(device_type), f"Device type {device_type}")
        except (TypeError, ValueError):
            label = str(device_type)
        if label not in device_labels:
            device_labels.append(label)

    software_version = None
    if row.get("software_major_version") is not None:
        software_parts = [
            row.get("software_major_version"),
            row.get("software_minor_version"),
            row.get("software_build_version"),
        ]
        software_version = ".".join(
            str(part) for part in software_parts if part is not None
        )

    details = {
        "description": _plain(row.get("description")),
        "server_name": _plain(row.get("server_name")),
        "machine_name": _plain(row.get("machine_name")),
        "recovery_model": _plain(row.get("recovery_model")),
        "software_version": software_version,
        "first_lsn": _plain(row.get("first_lsn")),
        "last_lsn": _plain(row.get("last_lsn")),
        "checkpoint_lsn": _plain(row.get("checkpoint_lsn")),
        "database_backup_lsn": _plain(row.get("database_backup_lsn")),
        "expiration_date": _plain(row.get("expiration_date")),
        "backup_position": _plain(row.get("position")),
        "database_version": _plain(row.get("database_version")),
        "compatibility_level": _plain(row.get("compatibility_level")),
        "collation_name": _plain(row.get("collation_name")),
        "password_protected": (
            bool(row["is_password_protected"])
            if row.get("is_password_protected") is not None
            else None
        ),
        "encryption_algorithm": _plain(row.get("key_algorithm")),
        "encryptor_type": _plain(row.get("encryptor_type")),
        "has_backup_checksums": (
            bool(row["has_backup_checksums"])
            if row.get("has_backup_checksums") is not None
            else None
        ),
        "copy_only": (
            bool(row["is_copy_only"])
            if row.get("is_copy_only") is not None
            else None
        ),
        "media_set_id": media_set_id,
    }

    if media_rows:
        logical_names = [
            str(item["logical_device_name"])
            for item in media_rows
            if item.get("logical_device_name")
        ]
        family_numbers = [
            str(item["family_sequence_number"])
            for item in media_rows
            if item.get("family_sequence_number") is not None
        ]
        if logical_names:
            details["logical_devices"] = ", ".join(logical_names)
        if family_numbers:
            details["media_family_sequence"] = ", ".join(family_numbers)

    details = {key: value for key, value in details.items() if value is not None}

    return {
        "backup_id": str(backup_set_id),
        "database_name": row.get("database_name"),
        "kind": _SQLSERVER_BACKUP_KIND.get(native_type, "other"),
        "native_type": native_type or None,
        "status": "successful",
        "native_status": "COMPLETED",
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_seconds,
        "input_bytes": backup_size,
        "output_bytes": compressed_size if compressed_size is not None else backup_size,
        "backup_size_bytes": compressed_size if compressed_size is not None else backup_size,
        "destinations": destinations,
        "device_type": ", ".join(device_labels) or None,
        "label": row.get("name"),
        "owner": row.get("user_name"),
        "details": details,
    }


def _latest(items: list[dict], *kinds: str) -> dict | None:
    for item in items:
        if item["kind"] in kinds:
            return item
    return None


def _get_sqlserver_backups_sync(connection: dict, history_filter: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            target_database = connection.get("database") or identity.database_name
            cursor = db.cursor()
            try:
                if not target_database:
                    raise AppError(
                        "SQL Server backup monitoring requires a database name.",
                        code="SQLSERVER_BACKUP_DATABASE_REQUIRED",
                        status_code=400,
                    )

                try:
                    cursor.execute(
                        "SELECT name, CAST(DATABASEPROPERTYEX(name, 'Recovery') AS varchar(32)) "
                        "FROM master.dbo.sysdatabases WHERE name = ?",
                        (target_database,),
                    )
                    recovery_row = cursor.fetchone()
                    recovery_model = (
                        str(recovery_row[1])
                        if recovery_row and recovery_row[1] is not None
                        else None
                    )
                except Exception as exc:
                    warnings.append(
                        "Database recovery-model discovery unavailable: "
                        f"{sqlserver_error_message(exc)}"
                    )
                    recovery_model = None

                try:
                    backup_rows, extended_metadata = _fetch_backup_rows(
                        cursor,
                        identity,
                        target_database,
                        history_filter,
                        limit=BACKUP_HISTORY_LIMIT + 1,
                    )
                    latest_rows, latest_extended = _fetch_backup_rows(
                        cursor,
                        identity,
                        target_database,
                        None,
                        limit=1,
                    )
                except Exception as exc:
                    return {
                        "available": False,
                        "source": "msdb backup history",
                        "scope": "database",
                        "database_name": target_database,
                        "generation": identity.version.generation,
                        "latest_backup": None,
                        "summaries": [],
                        "items": [],
                        "truncated": False,
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

                if not extended_metadata or not latest_extended:
                    warnings.append(
                        "This SQL Server exposes the core backup history, but some "
                        "newer backup metadata columns are unavailable on this version."
                    )

                truncated = len(backup_rows) > BACKUP_HISTORY_LIMIT
                backup_rows = backup_rows[:BACKUP_HISTORY_LIMIT]

                media_ids = sorted(
                    {
                        int(row["media_set_id"])
                        for row in [*backup_rows, *latest_rows]
                        if row.get("media_set_id") is not None
                    }
                )
                media: dict[int, list[dict]] = {}
                if media_ids:
                    try:
                        media, extended_media = _fetch_media(cursor, media_ids)
                        if not extended_media:
                            warnings.append(
                                "Backup destinations are visible, but detailed media-device "
                                "metadata is unavailable on this SQL Server version."
                            )
                    except Exception as exc:
                        warnings.append(
                            "Backup destination history unavailable: "
                            f"{sqlserver_error_message(exc)}"
                        )
            finally:
                cursor.close()

            items = [_backup_item(row, media) for row in backup_rows]
            latest_backup = _backup_item(latest_rows[0], media) if latest_rows else None

            summary = {
                "database_name": str(target_database),
                "recovery_model": recovery_model,
                "last_full": _latest(items, "full"),
                "last_differential": _latest(items, "differential"),
                "last_incremental": None,
                "last_log": _latest(items, "log"),
            }

            if not backup_rows:
                warnings.append(
                    "No SQL Server backup sets were recorded for this database in the selected range."
                )

            notes = [
                "SQL Server msdb backupset contains completed backup sets; it is not a "
                "universal record of every failed backup attempt."
            ]
            if truncated:
                notes.append(
                    f"The selected range returned more than {BACKUP_HISTORY_LIMIT} backup sets; "
                    "only the newest records are shown. Narrow the custom date range for the full list."
                )

            return {
                "available": True,
                "source": "msdb backup history",
                "scope": "database",
                "database_name": str(target_database),
                "generation": identity.version.generation,
                "latest_backup": latest_backup,
                "summaries": [summary],
                "items": items,
                "truncated": truncated,
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


async def get_sqlserver_backups(connection: dict, history_filter: dict) -> dict:
    return await asyncio.to_thread(
        _get_sqlserver_backups_sync,
        connection,
        history_filter,
    )
