import asyncio
import re

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
    sqlserver_error_message,
)
from app.core.exceptions import AppError


_SIMPLE_PERMISSION = re.compile(r"^[A-Za-z][A-Za-z ]{0,63}$")


def _qident(value: str) -> str:
    return "[" + str(value).replace("]", "]]" ) + "]"


def _qliteral(value: str) -> str:
    return "N'" + str(value).replace("'", "''") + "'"


def _database_name(connection: dict) -> str:
    name = (connection.get("database") or "").strip()
    if not name:
        raise AppError(
            "This SQL Server operation requires a target database on the connection.",
            code="SQLSERVER_DATABASE_REQUIRED",
            status_code=400,
        )
    return name


def _execute_sqlserver(connection: dict, callback):
    try:
        with open_sqlserver_connection(connection) as db:
            return callback(db)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_OPERATION_FAILED",
            status_code=400,
        ) from exc


def _session_sync(connection: dict, data) -> dict:
    def run(db):
        cursor = db.cursor()
        try:
            cursor.execute("SELECT @@SPID")
            row = cursor.fetchone()
            own_spid = int(row[0]) if row else None
            if own_spid == data.session_id:
                raise AppError(
                    "DBAChum will not terminate its own SQL Server session.",
                    code="SQLSERVER_SELF_SESSION_PROTECTED",
                    status_code=400,
                )
            if data.action.value not in {"terminate", "disconnect", "cancel_query"}:
                raise AppError("Unsupported SQL Server session operation.", status_code=400)
            # SQL Server has no portable request-only cancel statement across
            # supported legacy generations. KILL is the native operation.
            statement = f"KILL {int(data.session_id)}"
            cursor.execute(statement)
            return {"target": str(data.session_id), "statement": statement}
        finally:
            cursor.close()
    return _execute_sqlserver(connection, run)


async def sqlserver_session_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_session_sync, connection, data)


def _storage_sync(connection: dict, data) -> dict:
    database_name = _database_name(connection)

    def run(db):
        cursor = db.cursor()
        try:
            cursor.execute(f"USE {_qident(database_name)}")
            if data.action.value == "resize_file":
                logical_name = (data.logical_name or data.file_name or "").strip()
                if not logical_name:
                    raise AppError(
                        "SQL Server resize requires logical_name.",
                        code="SQLSERVER_LOGICAL_FILE_REQUIRED",
                        status_code=400,
                    )
                cursor.execute(
                    "SELECT name, physical_name, CAST(size AS bigint) * 8192 "
                    "FROM sys.database_files WHERE name = ?",
                    logical_name,
                )
                row = cursor.fetchone()
                if not row:
                    # SQL Server 2005/legacy compatibility.
                    cursor.execute(
                        "SELECT name, filename, CAST(size AS bigint) * 8192 "
                        "FROM dbo.sysfiles WHERE name = ?",
                        logical_name,
                    )
                    row = cursor.fetchone()
                if not row:
                    raise AppError(
                        "SQL Server database file was not found.",
                        code="SQLSERVER_FILE_NOT_FOUND",
                        status_code=404,
                    )
                before = {
                    "logical_name": row[0],
                    "physical_name": row[1],
                    "size_bytes": int(row[2] or 0),
                }
                statement = (
                    f"ALTER DATABASE {_qident(database_name)} MODIFY FILE "
                    f"(NAME = {_qliteral(logical_name)}, SIZE = {data.size_mb}MB)"
                )
                cursor.execute(statement)
                return {
                    "target": logical_name,
                    "before": before,
                    "after": {**before, "size_bytes": data.size_mb * 1024 * 1024},
                    "statement": statement,
                }

            if data.action.value == "add_file":
                if not data.logical_name or not data.physical_name:
                    raise AppError(
                        "SQL Server add-file requires logical_name and physical_name.",
                        code="SQLSERVER_FILE_DETAILS_REQUIRED",
                        status_code=400,
                    )
                clause = "ADD LOG FILE" if data.file_type == "log" else "ADD FILE"
                parts = [
                    f"ALTER DATABASE {_qident(database_name)} {clause}",
                    "(",
                    f"NAME = {_qliteral(data.logical_name)},",
                    f"FILENAME = {_qliteral(data.physical_name)},",
                    f"SIZE = {data.size_mb}MB",
                ]
                if data.growth_mb:
                    parts[-1] += ","
                    parts.append(f"FILEGROWTH = {data.growth_mb}MB")
                if data.max_size_mb:
                    parts[-1] += ","
                    parts.append(f"MAXSIZE = {data.max_size_mb}MB")
                parts.append(")")
                statement = " ".join(parts)
                cursor.execute(statement)
                return {
                    "target": data.logical_name,
                    "before": None,
                    "after": {
                        "logical_name": data.logical_name,
                        "physical_name": data.physical_name,
                        "size_bytes": data.size_mb * 1024 * 1024,
                        "file_type": data.file_type,
                    },
                    "statement": statement,
                }

            raise AppError("Unsupported SQL Server storage operation.", status_code=400)
        finally:
            cursor.close()

    return _execute_sqlserver(connection, run)


async def sqlserver_storage_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_storage_sync, connection, data)


def _account_sync(connection: dict, data) -> dict:
    def run(db):
        cursor = db.cursor()
        try:
            login = _qident(data.account_name)
            if data.action.value == "enable":
                statement = f"ALTER LOGIN {login} ENABLE"
            elif data.action.value == "disable":
                statement = f"ALTER LOGIN {login} DISABLE"
            elif data.action.value == "reset_password":
                statement = (
                    f"ALTER LOGIN {login} WITH PASSWORD = {_qliteral(data.password or '')}"
                )
            else:
                raise AppError("Unsupported SQL Server account operation.", status_code=400)
            cursor.execute(statement)
            return {"target": data.account_name, "statement": statement}
        finally:
            cursor.close()
    return _execute_sqlserver(connection, run)


async def sqlserver_account_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_account_sync, connection, data)


def _access_sync(connection: dict, data) -> dict:
    database_name = _database_name(connection)

    def run(db):
        cursor = db.cursor()
        try:
            principal = data.principal.strip()
            if data.action.value in {"grant_role", "revoke_role"}:
                role = (data.role_name or "").strip()
                if data.scope == "server":
                    proc = "sp_addsrvrolemember" if data.action.value == "grant_role" else "sp_dropsrvrolemember"
                    statement = f"EXEC master.dbo.{proc} @loginame = {_qliteral(principal)}, @rolename = {_qliteral(role)}"
                else:
                    cursor.execute(f"USE {_qident(database_name)}")
                    proc = "sp_addrolemember" if data.action.value == "grant_role" else "sp_droprolemember"
                    statement = f"EXEC dbo.{proc} @rolename = {_qliteral(role)}, @membername = {_qliteral(principal)}"
            else:
                privilege = (data.privilege or "").strip().upper()
                if not _SIMPLE_PERMISSION.fullmatch(privilege):
                    raise AppError(
                        "Invalid SQL Server privilege name.",
                        code="SQLSERVER_PRIVILEGE_INVALID",
                        status_code=400,
                    )
                object_name = (data.object_name or "").strip()
                if not object_name:
                    raise AppError("object_name is required.", status_code=400)
                cursor.execute(f"USE {_qident(database_name)}")
                verb = "GRANT" if data.action.value == "grant_privilege" else "REVOKE"
                # Object name may be schema.object. Quote each component instead
                # of accepting arbitrary SQL text.
                quoted_object = ".".join(_qident(part) for part in object_name.split(".") if part)
                if not quoted_object:
                    raise AppError("Invalid SQL Server object name.", status_code=400)
                statement = f"{verb} {privilege} ON {quoted_object} TO {_qident(principal)}"
            cursor.execute(statement)
            return {"target": principal, "statement": statement}
        finally:
            cursor.close()

    return _execute_sqlserver(connection, run)


async def sqlserver_access_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_access_sync, connection, data)
