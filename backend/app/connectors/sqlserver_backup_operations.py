import asyncio
from datetime import datetime, timezone

from app.connectors.sqlserver_compat import open_sqlserver_connection, sqlserver_error_message
from app.core.exceptions import AppError


def _qident(value: str) -> str:
    return "[" + str(value).replace("]", "]]" ) + "]"


def _qliteral(value: str) -> str:
    return "N'" + str(value).replace("'", "''") + "'"


def _backup_sync(connection: dict, data) -> dict:
    database_name = (connection.get("database") or "").strip()
    if not database_name:
        raise AppError(
            "SQL Server backup requires a database name on the connection.",
            code="SQLSERVER_BACKUP_DATABASE_REQUIRED",
            status_code=400,
        )
    destination = (data.destination or "").strip()
    if not destination:
        raise AppError(
            "SQL Server backup requires a destination path visible to the SQL Server service account.",
            code="SQLSERVER_BACKUP_DESTINATION_REQUIRED",
            status_code=400,
        )

    action = data.action.value
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if destination.endswith("\\") or destination.endswith("/"):
        extension = "trn" if action == "log" else "bak"
        destination = destination + f"{database_name}_{timestamp}.{extension}"

    if action == "full":
        command = f"BACKUP DATABASE {_qident(database_name)} TO DISK = {_qliteral(destination)}"
        options = ["INIT", "STATS = 10"]
        if data.copy_only:
            options.append("COPY_ONLY")
    elif action == "differential":
        command = f"BACKUP DATABASE {_qident(database_name)} TO DISK = {_qliteral(destination)}"
        options = ["DIFFERENTIAL", "INIT", "STATS = 10"]
        if data.copy_only:
            options.append("COPY_ONLY")
    elif action == "log":
        command = f"BACKUP LOG {_qident(database_name)} TO DISK = {_qliteral(destination)}"
        options = ["INIT", "STATS = 10"]
    else:
        raise AppError(
            "SQL Server backup supports full, differential, or log.",
            code="SQLSERVER_BACKUP_TYPE_UNSUPPORTED",
            status_code=400,
        )

    statement = command + " WITH " + ", ".join(options)
    try:
        with open_sqlserver_connection(connection) as db:
            cursor = db.cursor()
            try:
                cursor.execute(statement)
                # Some providers expose informational messages only after the
                # result stream is drained. Consume result sets until done.
                while True:
                    try:
                        if not cursor.nextset():
                            break
                    except Exception:
                        break
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_BACKUP_FAILED",
            status_code=400,
        ) from exc

    return {
        "target": database_name,
        "backup_type": action,
        "destination": destination,
        "statement": statement,
    }


async def sqlserver_backup_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_backup_sync, connection, data)
