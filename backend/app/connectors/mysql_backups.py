from datetime import datetime, timezone


async def get_mysql_backups(connection: dict) -> dict:
    # MySQL does not expose one universal native backup-history repository.
    # mysqldump, XtraBackup, Enterprise Backup, snapshots, and custom tooling
    # all need a provider-specific adapter. Keep the API stable now so those
    # providers can be added without redesigning the UI later.
    return {
        "available": False,
        "source": "external backup provider required",
        "scope": "external",
        "database_name": connection.get("database"),
        "generation": None,
        "summaries": [],
        "items": [],
        "warnings": [],
        "notes": [
            "MySQL has no single universal native backup-history source. Configure "
            "a provider such as mysqldump, XtraBackup, Enterprise Backup, or snapshots."
        ],
        "checked_at": datetime.now(timezone.utc),
    }
