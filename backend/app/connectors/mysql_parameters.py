import asyncio
import re
from datetime import datetime, timezone

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError

from app.connectors.mysql import (
    _close_mysql_resource,
    _read_mysql_identity,
    mysql_connect_kwargs,
)
from app.core.exceptions import AppError


_PARAMETER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _name(value: str) -> str:
    candidate = (value or "").strip()
    if not _PARAMETER_RE.fullmatch(candidate):
        raise AppError(
            "Invalid MySQL/MariaDB variable name.",
            code="MYSQL_PARAMETER_INVALID",
            status_code=400,
        )
    return candidate


def _parameters_sync(connection: dict) -> dict:
    db = None
    cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        identity = _read_mysql_identity(cursor)
        cursor.execute("SHOW GLOBAL VARIABLES")
        items = [
            {
                "name": str(row[0]),
                "value": None if row[1] is None else str(row[1]),
                "display_value": None if row[1] is None else str(row[1]),
                "runtime_value": None if row[1] is None else str(row[1]),
                "source": "SHOW GLOBAL VARIABLES",
            }
            for row in cursor.fetchall()
        ]
        return {
            "scope": "server",
            "generation": identity["version_info"].generation,
            "available": True,
            "items": items,
            "warnings": [
                "MySQL/MariaDB does not expose one portable dynamic/static flag across all supported generations; unsupported SET operations are rejected by the server."
            ],
            "checked_at": datetime.now(timezone.utc),
        }
    except AppError:
        raise
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_PARAMETERS_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def get_mysql_parameters(connection: dict) -> dict:
    return await asyncio.to_thread(_parameters_sync, connection)


def _parameter_operation_sync(connection: dict, data) -> dict:
    db = None
    cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        identity = _read_mysql_identity(cursor)
        version = identity["version_info"]
        name = _name(data.name)

        cursor.execute(f"SHOW GLOBAL VARIABLES LIKE '{name}'")
        row = cursor.fetchone()
        if not row:
            raise AppError(
                "MySQL/MariaDB global variable was not found.",
                code="MYSQL_PARAMETER_NOT_FOUND",
                status_code=404,
            )
        before = {"name": name, "runtime_value": None if row[1] is None else str(row[1])}

        supports_persist = bool(
            not version.mariadb
            and version.major is not None
            and version.major >= 8
        )
        if data.apply_mode in {"persistent", "both"} and not supports_persist:
            raise AppError(
                "Persistent variable changes require MySQL 8 SET PERSIST. This generation can only be changed at runtime from DBAChum; update its server configuration file for restart persistence.",
                code="MYSQL_PARAMETER_PERSIST_UNSUPPORTED",
                status_code=400,
            )

        verb = {
            "runtime": "GLOBAL",
            "persistent": "PERSIST_ONLY",
            "both": "PERSIST",
        }[data.apply_mode]
        statement = f"SET {verb} `{name}` = %s"
        cursor.execute(statement, (data.value,))
        cursor.execute(f"SHOW GLOBAL VARIABLES LIKE '{name}'")
        after_row = cursor.fetchone()
        after = {
            "name": name,
            "runtime_value": None if not after_row or after_row[1] is None else str(after_row[1]),
            "persistent": verb in {"PERSIST", "PERSIST_ONLY"},
            "runtime_changed": verb != "PERSIST_ONLY",
        }
        return {
            "target": name,
            "before": before,
            "after": after,
            "statement": f"SET {verb} `{name}` = <value>",
        }
    except AppError:
        raise
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_PARAMETER_OPERATION_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def mysql_parameter_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_parameter_operation_sync, connection, data)
