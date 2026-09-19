import asyncio
from datetime import date, datetime
from decimal import Decimal

import mysql.connector as mysql_connector

from app.connectors.mysql import mysql_connect_kwargs
from app.connectors.oracle_metadata import (
    list_oracle_columns,
    list_oracle_schemas,
    list_oracle_tables,
)
from app.connectors.oracle_user_list_enrichment import fetch_oracle_user_list_values_multi
from app.connectors.sqlserver_compat import open_sqlserver_connection, sqlserver_error_message
from app.core.exceptions import AppError


MAX_BIND_VALUES = 500

ORACLE_TEXT_TYPES = {"CHAR", "NCHAR", "VARCHAR2", "NVARCHAR2"}
SQLSERVER_TEXT_TYPES = {"CHAR", "NCHAR", "VARCHAR", "NVARCHAR", "TEXT", "NTEXT"}
MYSQL_TEXT_TYPES = {
    "CHAR",
    "VARCHAR",
    "TINYTEXT",
    "TEXT",
    "MEDIUMTEXT",
    "LONGTEXT",
    "ENUM",
    "SET",
}


def _display_value(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return value.hex()
    return str(value)


def _chunks(values: list[str], size: int = MAX_BIND_VALUES):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _quote_sqlserver_identifier(value: str) -> str:
    return f"[{value.replace(']', ']]')}]"


def _quote_mysql_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def source_join_type_supported(engine: str, data_type: str) -> bool:
    normalized = str(data_type or "").strip().upper()
    if engine == "oracle":
        return normalized in ORACLE_TEXT_TYPES
    if engine == "sqlserver":
        return normalized in SQLSERVER_TEXT_TYPES
    if engine == "mysql":
        return normalized in MYSQL_TEXT_TYPES
    return False


async def list_user_list_source_schemas(connection: dict) -> list[dict]:
    engine = connection.get("engine")
    if engine == "oracle":
        return await list_oracle_schemas(connection)
    if engine == "sqlserver":
        return await asyncio.to_thread(_list_sqlserver_schemas_sync, connection)
    if engine == "mysql":
        return await asyncio.to_thread(_list_mysql_schemas_sync, connection)
    raise AppError("Unsupported database engine.", code="USER_LIST_SOURCE_ENGINE_UNSUPPORTED", status_code=400)


async def list_user_list_source_tables(connection: dict, owner: str) -> list[dict]:
    engine = connection.get("engine")
    if engine == "oracle":
        return await list_oracle_tables(connection, owner)
    if engine == "sqlserver":
        return await asyncio.to_thread(_list_sqlserver_tables_sync, connection, owner)
    if engine == "mysql":
        return await asyncio.to_thread(_list_mysql_tables_sync, connection, owner)
    raise AppError("Unsupported database engine.", code="USER_LIST_SOURCE_ENGINE_UNSUPPORTED", status_code=400)


async def list_user_list_source_columns(connection: dict, owner: str, table_name: str) -> list[dict]:
    engine = connection.get("engine")
    if engine == "oracle":
        return await list_oracle_columns(connection, owner, table_name)
    if engine == "sqlserver":
        return await asyncio.to_thread(_list_sqlserver_columns_sync, connection, owner, table_name)
    if engine == "mysql":
        return await asyncio.to_thread(_list_mysql_columns_sync, connection, owner, table_name)
    raise AppError("Unsupported database engine.", code="USER_LIST_SOURCE_ENGINE_UNSUPPORTED", status_code=400)


async def fetch_user_list_source_values_multi(
    connection: dict,
    keys: list[str],
    *,
    owner: str,
    table_name: str,
    join_column: str,
    display_columns: list[str],
) -> tuple[dict[str, dict[str, str | None]], set[str]]:
    engine = connection.get("engine")
    if engine == "oracle":
        return await fetch_oracle_user_list_values_multi(
            connection,
            keys,
            owner=owner,
            table_name=table_name,
            join_column=join_column,
            display_columns=display_columns,
        )
    if engine == "sqlserver":
        return await asyncio.to_thread(
            _fetch_sqlserver_values_sync,
            connection,
            keys,
            owner,
            table_name,
            join_column,
            display_columns,
        )
    if engine == "mysql":
        return await asyncio.to_thread(
            _fetch_mysql_values_sync,
            connection,
            keys,
            owner,
            table_name,
            join_column,
            display_columns,
        )
    raise AppError("Unsupported database engine.", code="USER_LIST_SOURCE_ENGINE_UNSUPPORTED", status_code=400)


def _list_sqlserver_schemas_sync(connection: dict) -> list[dict]:
    try:
        with open_sqlserver_connection(connection) as db:
            cursor = db.cursor()
            try:
                cursor.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA ORDER BY SCHEMA_NAME")
                return [{"name": str(row[0])} for row in cursor.fetchall()]
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(sqlserver_error_message(exc), code="USER_LIST_SOURCE_METADATA_FAILED", status_code=400) from exc


def _list_sqlserver_tables_sync(connection: dict, owner: str) -> list[dict]:
    try:
        with open_sqlserver_connection(connection) as db:
            cursor = db.cursor()
            try:
                cursor.execute(
                    """
                    SELECT TABLE_SCHEMA, TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_SCHEMA = ?
                      AND TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                    """,
                    owner,
                )
                return [{"owner": str(row[0]), "name": str(row[1])} for row in cursor.fetchall()]
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(sqlserver_error_message(exc), code="USER_LIST_SOURCE_METADATA_FAILED", status_code=400) from exc


def _list_sqlserver_columns_sync(connection: dict, owner: str, table_name: str) -> list[dict]:
    try:
        with open_sqlserver_connection(connection) as db:
            cursor = db.cursor()
            try:
                cursor.execute(
                    """
                    SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, COLUMN_DEFAULT, ORDINAL_POSITION
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
                    ORDER BY ORDINAL_POSITION
                    """,
                    owner,
                    table_name,
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(sqlserver_error_message(exc), code="USER_LIST_SOURCE_METADATA_FAILED", status_code=400) from exc
    if not rows:
        raise AppError("The selected table was not found or is not visible to this connection.", code="USER_LIST_SOURCE_TABLE_NOT_VISIBLE", status_code=404)
    return [
        {
            "name": str(row[0]),
            "data_type": str(row[1]),
            "data_length": int(row[2]) if row[2] is not None else None,
            "nullable": str(row[3]).upper() == "YES",
            "data_default": str(row[4]).strip() if row[4] is not None else None,
            "column_id": int(row[5]),
        }
        for row in rows
    ]


def _list_mysql_schemas_sync(connection: dict) -> list[dict]:
    db = None
    cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        cursor.execute("SELECT schema_name FROM information_schema.schemata ORDER BY schema_name")
        return [{"name": str(row[0])} for row in cursor.fetchall()]
    except Exception as exc:
        raise AppError(str(exc), code="USER_LIST_SOURCE_METADATA_FAILED", status_code=400) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


def _list_mysql_tables_sync(connection: dict, owner: str) -> list[dict]:
    db = None
    cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (owner,),
        )
        return [{"owner": str(row[0]), "name": str(row[1])} for row in cursor.fetchall()]
    except Exception as exc:
        raise AppError(str(exc), code="USER_LIST_SOURCE_METADATA_FAILED", status_code=400) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()


def _list_mysql_columns_sync(connection: dict, owner: str, table_name: str) -> list[dict]:
    db = None
    cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        cursor.execute(
            """
            SELECT column_name, data_type, character_maximum_length, is_nullable, column_default, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (owner, table_name),
        )
        rows = cursor.fetchall()
    except Exception as exc:
        raise AppError(str(exc), code="USER_LIST_SOURCE_METADATA_FAILED", status_code=400) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()
    if not rows:
        raise AppError("The selected table was not found or is not visible to this connection.", code="USER_LIST_SOURCE_TABLE_NOT_VISIBLE", status_code=404)
    return [
        {
            "name": str(row[0]),
            "data_type": str(row[1]),
            "data_length": int(row[2]) if row[2] is not None else None,
            "nullable": str(row[3]).upper() == "YES",
            "data_default": str(row[4]).strip() if row[4] is not None else None,
            "column_id": int(row[5]),
        }
        for row in rows
    ]


def _fetch_sqlserver_values_sync(
    connection: dict,
    keys: list[str],
    owner: str,
    table_name: str,
    join_column: str,
    display_columns: list[str],
) -> tuple[dict[str, dict[str, str | None]], set[str]]:
    values: dict[str, dict[str, str | None]] = {}
    duplicate_keys: set[str] = set()
    if not keys or not display_columns:
        return values, duplicate_keys
    table_ref = f"{_quote_sqlserver_identifier(owner)}.{_quote_sqlserver_identifier(table_name)}"
    join_ref = _quote_sqlserver_identifier(join_column)
    display_refs = [_quote_sqlserver_identifier(column) for column in display_columns]
    try:
        with open_sqlserver_connection(connection) as db:
            cursor = db.cursor()
            try:
                for chunk in _chunks(keys):
                    placeholders = ", ".join("?" for _ in chunk)
                    projection = ", ".join([join_ref, *display_refs])
                    requested_keys = {str(key).casefold(): str(key) for key in chunk}
                    cursor.execute(
                        f"SELECT {projection} FROM {table_ref} WHERE {join_ref} IN ({placeholders})",
                        *chunk,
                    )
                    for row in cursor.fetchall():
                        raw_key = "" if row[0] is None else str(row[0])
                        key = requested_keys.get(raw_key.casefold(), raw_key)
                        if not key:
                            continue
                        if key in values:
                            duplicate_keys.add(key)
                            continue
                        values[key] = {
                            column: _display_value(row[index + 1])
                            for index, column in enumerate(display_columns)
                        }
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(sqlserver_error_message(exc), code="USER_LIST_SOURCE_QUERY_FAILED", status_code=400) from exc
    return values, duplicate_keys


def _fetch_mysql_values_sync(
    connection: dict,
    keys: list[str],
    owner: str,
    table_name: str,
    join_column: str,
    display_columns: list[str],
) -> tuple[dict[str, dict[str, str | None]], set[str]]:
    values: dict[str, dict[str, str | None]] = {}
    duplicate_keys: set[str] = set()
    if not keys or not display_columns:
        return values, duplicate_keys
    table_ref = f"{_quote_mysql_identifier(owner)}.{_quote_mysql_identifier(table_name)}"
    join_ref = _quote_mysql_identifier(join_column)
    display_refs = [_quote_mysql_identifier(column) for column in display_columns]
    db = None
    cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        for chunk in _chunks(keys):
            placeholders = ", ".join("%s" for _ in chunk)
            projection = ", ".join([join_ref, *display_refs])
            requested_keys = {str(key).casefold(): str(key) for key in chunk}
            cursor.execute(
                f"SELECT {projection} FROM {table_ref} WHERE {join_ref} IN ({placeholders})",
                tuple(chunk),
            )
            for row in cursor.fetchall():
                raw_key = "" if row[0] is None else str(row[0])
                key = requested_keys.get(raw_key.casefold(), raw_key)
                if not key:
                    continue
                if key in values:
                    duplicate_keys.add(key)
                    continue
                values[key] = {
                    column: _display_value(row[index + 1])
                    for index, column in enumerate(display_columns)
                }
    except Exception as exc:
        raise AppError(str(exc), code="USER_LIST_SOURCE_QUERY_FAILED", status_code=400) from exc
    finally:
        if cursor is not None:
            cursor.close()
        if db is not None:
            db.close()
    return values, duplicate_keys
