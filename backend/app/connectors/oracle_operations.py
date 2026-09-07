import re

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.core.exceptions import AppError


_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")


def _oracle_identifier(value: str, field_name: str) -> str:
    candidate = (value or "").strip()
    if not _IDENTIFIER_RE.fullmatch(candidate):
        raise AppError(
            f"Invalid Oracle {field_name}.",
            code="ORACLE_OPERATION_IDENTIFIER_INVALID",
            status_code=400,
        )
    return f'"{candidate.upper()}"'


def _oracle_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


async def oracle_session_operation(connection: dict, data) -> dict:
    if data.serial_number is None:
        raise AppError(
            "Oracle session operations require SID and SERIAL#.",
            code="ORACLE_SESSION_SERIAL_REQUIRED",
            status_code=400,
        )

    target = f"{data.session_id},{data.serial_number}"
    if data.action.value == "terminate":
        statement = f"ALTER SYSTEM KILL SESSION '{target}' IMMEDIATE"
    elif data.action.value == "disconnect":
        statement = f"ALTER SYSTEM DISCONNECT SESSION '{target}' IMMEDIATE"
    elif data.action.value == "cancel_query":
        # ALTER SYSTEM CANCEL SQL is not available on Oracle 10g. Keep the
        # compatibility contract explicit rather than silently killing a
        # session when the caller asked only to cancel its SQL.
        async with open_oracle_connection(connection) as db:
            try:
                major = int(str(db.version).split(".", 1)[0])
            except (TypeError, ValueError):
                major = None
            if major is None or major < 18:
                raise AppError(
                    "Cancel SQL is not supported by this Oracle generation. "
                    "Use terminate or disconnect instead.",
                    code="ORACLE_CANCEL_SQL_UNSUPPORTED",
                    status_code=400,
                )
            statement = f"ALTER SYSTEM CANCEL SQL '{target}'"
            try:
                await db.execute(statement)
            except oracledb.Error as exc:
                raise AppError(
                    oracle_error_message(exc),
                    code="ORACLE_SESSION_OPERATION_FAILED",
                    status_code=400,
                ) from exc
            return {"target": target, "statement": statement}
    else:
        raise AppError("Unsupported Oracle session operation.", status_code=400)

    try:
        async with open_oracle_connection(connection) as db:
            await db.execute(statement)
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_SESSION_OPERATION_FAILED",
            status_code=400,
        ) from exc

    return {"target": target, "statement": statement}


async def _resolve_oracle_datafile(db, *, file_id=None, file_name=None):
    if file_id is not None:
        row = await db.fetchone(
            "SELECT file_id, file_name, tablespace_name, bytes FROM dba_data_files WHERE file_id = :file_id",
            {"file_id": file_id},
        )
    elif file_name:
        row = await db.fetchone(
            "SELECT file_id, file_name, tablespace_name, bytes FROM dba_data_files WHERE file_name = :file_name",
            {"file_name": file_name},
        )
    else:
        row = None

    if not row:
        raise AppError(
            "Oracle datafile was not found or is not visible to this login.",
            code="ORACLE_DATAFILE_NOT_FOUND",
            status_code=404,
        )
    return {
        "file_id": int(row[0]),
        "file_name": row[1],
        "tablespace_name": row[2],
        "size_bytes": int(row[3] or 0),
    }


async def oracle_storage_operation(connection: dict, data) -> dict:
    try:
        async with open_oracle_connection(connection) as db:
            if data.action.value == "resize_file":
                before = await _resolve_oracle_datafile(
                    db,
                    file_id=data.file_id,
                    file_name=data.file_name,
                )
                statement = (
                    "ALTER DATABASE DATAFILE "
                    f"{_oracle_literal(before['file_name'])} RESIZE {data.size_mb}M"
                )
                await db.execute(statement)
                after = await _resolve_oracle_datafile(db, file_id=before["file_id"])
                return {
                    "target": before["file_name"],
                    "before": before,
                    "after": after,
                    "statement": statement,
                }

            if data.action.value == "create_tablespace":
                if not data.tablespace_name:
                    raise AppError(
                        "Oracle create-tablespace requires tablespace_name.",
                        code="ORACLE_TABLESPACE_REQUIRED",
                        status_code=400,
                    )
                tablespace = _oracle_identifier(data.tablespace_name, "tablespace name")
                pieces = [f"CREATE TABLESPACE {tablespace} DATAFILE"]
                if data.physical_name:
                    pieces.append(_oracle_literal(data.physical_name))
                pieces.append(f"SIZE {data.size_mb}M")
                if data.autoextend:
                    growth = data.growth_mb or max(1, min(data.size_mb, 1024))
                    pieces.append(f"AUTOEXTEND ON NEXT {growth}M")
                    if data.max_size_mb:
                        pieces.append(f"MAXSIZE {data.max_size_mb}M")
                    else:
                        pieces.append("MAXSIZE UNLIMITED")
                statement = " ".join(pieces)
                await db.execute(statement)
                row = await db.fetchone(
                    "SELECT tablespace_name, status, contents FROM dba_tablespaces WHERE tablespace_name = :name",
                    {"name": data.tablespace_name.upper()},
                )
                return {
                    "target": data.tablespace_name.upper(),
                    "before": None,
                    "after": {
                        "tablespace_name": row[0] if row else data.tablespace_name.upper(),
                        "status": row[1] if row else None,
                        "contents": row[2] if row else None,
                        "size_mb": data.size_mb,
                    },
                    "statement": statement,
                }

            if data.action.value == "add_file":
                if not data.tablespace_name:
                    raise AppError(
                        "Oracle add-file requires tablespace_name.",
                        code="ORACLE_TABLESPACE_REQUIRED",
                        status_code=400,
                    )
                tablespace = _oracle_identifier(data.tablespace_name, "tablespace name")
                pieces = [f"ALTER TABLESPACE {tablespace} ADD DATAFILE"]
                if data.physical_name:
                    pieces.append(_oracle_literal(data.physical_name))
                pieces.append(f"SIZE {data.size_mb}M")
                if data.autoextend:
                    growth = data.growth_mb or max(1, min(data.size_mb, 1024))
                    pieces.append(f"AUTOEXTEND ON NEXT {growth}M")
                    if data.max_size_mb:
                        pieces.append(f"MAXSIZE {data.max_size_mb}M")
                    else:
                        pieces.append("MAXSIZE UNLIMITED")
                else:
                    pieces.append("AUTOEXTEND OFF")
                statement = " ".join(pieces)
                await db.execute(statement)
                return {
                    "target": data.physical_name or data.tablespace_name,
                    "before": None,
                    "after": {
                        "tablespace_name": data.tablespace_name.upper(),
                        "size_mb": data.size_mb,
                        "physical_name": data.physical_name,
                    },
                    "statement": statement,
                }

            raise AppError("Unsupported Oracle storage operation.", status_code=400)
    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_STORAGE_OPERATION_FAILED",
            status_code=400,
        ) from exc
