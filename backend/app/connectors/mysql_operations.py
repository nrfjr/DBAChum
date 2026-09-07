import asyncio
import re

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError

from app.connectors.mysql import _close_mysql_resource, _read_mysql_identity, mysql_connect_kwargs
from app.core.exceptions import AppError


_PRIVILEGE_RE = re.compile(r"^[A-Z][A-Z_ ]{0,63}$")
_OBJECT_PART_RE = re.compile(r"^[A-Za-z0-9_$*%.-]+$")


def _string_literal(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def _account(user: str, host: str | None) -> str:
    return f"{_string_literal(user)}@{_string_literal(host or '%')}"


def _object_scope(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate or not _OBJECT_PART_RE.fullmatch(candidate):
        raise AppError(
            "Invalid MySQL/MariaDB privilege object scope.",
            code="MYSQL_PRIVILEGE_SCOPE_INVALID",
            status_code=400,
        )
    if "." not in candidate:
        candidate = candidate + ".*"
    parts = candidate.split(".", 1)
    quoted = []
    for part in parts:
        if part == "*":
            quoted.append("*")
        else:
            quoted.append("`" + part.replace("`", "``") + "`")
    return ".".join(quoted)


def _connect(connection: dict):
    return mysql_connector.connect(**mysql_connect_kwargs(connection))


def _session_sync(connection: dict, data) -> dict:
    db = None
    cursor = None
    try:
        db = _connect(connection)
        cursor = db.cursor()
        cursor.execute("SELECT CONNECTION_ID()")
        row = cursor.fetchone()
        own_id = int(row[0]) if row else None
        if own_id == data.session_id:
            raise AppError(
                "DBAChum will not terminate its own MySQL/MariaDB connection.",
                code="MYSQL_SELF_SESSION_PROTECTED",
                status_code=400,
            )
        if data.action.value == "cancel_query":
            statement = f"KILL QUERY {int(data.session_id)}"
        elif data.action.value in {"terminate", "disconnect"}:
            statement = f"KILL CONNECTION {int(data.session_id)}"
        else:
            raise AppError("Unsupported MySQL/MariaDB session operation.", status_code=400)
        cursor.execute(statement)
        return {"target": str(data.session_id), "statement": statement}
    except AppError:
        raise
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_SESSION_OPERATION_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def mysql_session_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_session_sync, connection, data)


async def mysql_storage_operation(connection: dict, data) -> dict:
    raise AppError(
        "MySQL/MariaDB file growth is managed by the storage engine and server filesystem; "
        "DBAChum does not issue a fake generic resize/add-file command for this engine.",
        code="MYSQL_STORAGE_MUTATION_UNSUPPORTED",
        status_code=400,
    )


def _account_sync(connection: dict, data) -> dict:
    db = None
    cursor = None
    try:
        db = _connect(connection)
        cursor = db.cursor()
        identity = _read_mysql_identity(cursor)
        version = identity["version_info"]
        target = _account(data.account_name, data.host)

        if data.action.value in {"enable", "disable"}:
            # ACCOUNT LOCK/UNLOCK is broadly available in MySQL 5.7.6+ and
            # modern MariaDB. Reject old generations instead of emulating an
            # account lock by corrupting credentials.
            mysql_supported = (
                not version.mariadb
                and version.major is not None
                and (version.major, version.minor or 0) >= (5, 7)
            )
            mariadb_supported = (
                version.mariadb
                and version.major is not None
                and (version.major, version.minor or 0) >= (10, 4)
            )
            if not (mysql_supported or mariadb_supported):
                raise AppError(
                    "Native account lock/unlock is not supported by this MySQL/MariaDB generation.",
                    code="MYSQL_ACCOUNT_LOCK_UNSUPPORTED",
                    status_code=400,
                )
            keyword = "UNLOCK" if data.action.value == "enable" else "LOCK"
            statement = f"ALTER USER {target} ACCOUNT {keyword}"
            cursor.execute(statement)

        elif data.action.value == "reset_password":
            password = _string_literal(data.password or "")
            modern = (
                version.major is not None
                and (
                    version.mariadb
                    or (version.major, version.minor or 0) >= (5, 7)
                )
            )
            if modern:
                statement = f"ALTER USER {target} IDENTIFIED BY {password}"
            else:
                statement = f"SET PASSWORD FOR {target} = PASSWORD({password})"
            cursor.execute(statement)
        else:
            raise AppError("Unsupported MySQL/MariaDB account operation.", status_code=400)

        return {"target": f"{data.account_name}@{data.host or '%'}", "statement": statement}
    except AppError:
        raise
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_ACCOUNT_OPERATION_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def mysql_account_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_account_sync, connection, data)


def _access_sync(connection: dict, data) -> dict:
    db = None
    cursor = None
    try:
        db = _connect(connection)
        cursor = db.cursor()
        principal = _account(data.principal, data.host)
        if data.action.value in {"grant_role", "revoke_role"}:
            role = _account(data.role_name or "", "%")
            verb = "GRANT" if data.action.value == "grant_role" else "REVOKE"
            connector = "TO" if verb == "GRANT" else "FROM"
            statement = f"{verb} {role} {connector} {principal}"
        else:
            privilege = (data.privilege or "").strip().upper()
            if not _PRIVILEGE_RE.fullmatch(privilege):
                raise AppError(
                    "Invalid MySQL/MariaDB privilege name.",
                    code="MYSQL_PRIVILEGE_INVALID",
                    status_code=400,
                )
            scope = _object_scope(data.object_name or "")
            verb = "GRANT" if data.action.value == "grant_privilege" else "REVOKE"
            connector = "TO" if verb == "GRANT" else "FROM"
            statement = f"{verb} {privilege} ON {scope} {connector} {principal}"
        cursor.execute(statement)
        return {"target": f"{data.principal}@{data.host or '%'}", "statement": statement}
    except AppError:
        raise
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_ACCESS_OPERATION_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def mysql_access_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_access_sync, connection, data)
