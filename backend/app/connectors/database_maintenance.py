import asyncio
import re
from datetime import datetime, timezone

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError
import oracledb

from app.connectors.mysql import _close_mysql_resource, mysql_connect_kwargs
from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.connectors.sqlserver_compat import open_sqlserver_connection, sqlserver_error_message
from app.core.exceptions import AppError


_SIMPLE_NAME = re.compile(r"^[A-Za-z0-9_$#.-]+$")


def _oracle_name(value: str | None, label: str) -> str:
    candidate = (value or "").strip()
    if not candidate or not _SIMPLE_NAME.fullmatch(candidate):
        raise AppError(f"Invalid Oracle {label}.", status_code=400)
    return candidate.upper()


async def oracle_database_maintenance(connection: dict, data) -> dict:
    action = data.action.value
    try:
        async with open_oracle_connection(connection) as db:
            if action == "gather_schema_stats":
                owner = _oracle_name(data.schema_name or connection.get("username"), "schema name")
                statement = "BEGIN DBMS_STATS.GATHER_SCHEMA_STATS(:owner, options => 'GATHER AUTO'); END;"
                await db.execute(statement, {"owner": owner})
                await db.commit()
                return {"target": owner, "statement": statement}

            if action == "gather_table_stats":
                owner = _oracle_name(data.schema_name or connection.get("username"), "schema name")
                table = _oracle_name(data.table_name, "table name")
                statement = "BEGIN DBMS_STATS.GATHER_TABLE_STATS(:owner, :table_name, cascade => TRUE); END;"
                await db.execute(statement, {"owner": owner, "table_name": table})
                await db.commit()
                return {"target": f"{owner}.{table}", "statement": statement}

            if action == "recompile_invalid":
                statement = "BEGIN UTL_RECOMP.RECOMP_SERIAL(); END;"
                await db.execute(statement)
                await db.commit()
                return {"target": connection.get("oracle_identifier") or connection.get("name"), "statement": statement}

            if action == "rebuild_unusable_indexes":
                rows = await db.fetchall(
                    """
                    SELECT owner, index_name
                    FROM all_indexes
                    WHERE status = 'UNUSABLE'
                      AND owner NOT IN ('SYS', 'SYSTEM')
                    ORDER BY owner, index_name
                    """
                )
                rebuilt = 0
                for owner, index_name in rows:
                    owner_name = _oracle_name(str(owner), "index owner")
                    index = _oracle_name(str(index_name), "index name")
                    await db.execute(f'ALTER INDEX "{owner_name}"."{index}" REBUILD')
                    rebuilt += 1
                await db.commit()
                return {
                    "target": f"{rebuilt} unusable index(es)",
                    "after": {"rebuilt_indexes": rebuilt},
                    "statement": "ALTER INDEX ... REBUILD",
                }

            if action == "purge_recyclebin":
                statement = "PURGE RECYCLEBIN"
                await db.execute(statement)
                return {"target": connection.get("username"), "statement": statement}

            raise AppError("Unsupported Oracle database maintenance operation.", status_code=400)
    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(oracle_error_message(exc), code="ORACLE_DATABASE_MAINTENANCE_FAILED", status_code=400) from exc


def _sqlserver_qident(value: str) -> str:
    return "[" + str(value).replace("]", "]]" ) + "]"


def _sqlserver_maintenance_sync(connection: dict, data) -> dict:
    action = data.action.value
    try:
        with open_sqlserver_connection(connection) as db:
            cursor = db.cursor()
            try:
                database_name = str(connection.get("database") or "master")
                if action == "check_integrity":
                    statement = f"DBCC CHECKDB ({_sqlserver_qident(database_name)}) WITH NO_INFOMSGS"
                    cursor.execute(statement)
                    try:
                        while True:
                            cursor.fetchall()
                            if not cursor.nextset():
                                break
                    except Exception:
                        pass
                    return {"target": database_name, "statement": statement}

                if action == "update_statistics":
                    cursor.execute(f"USE {_sqlserver_qident(database_name)}")
                    if data.table_name:
                        table = str(data.table_name).strip()
                        if not table or ";" in table:
                            raise AppError("Invalid SQL Server table name.", status_code=400)
                        parts = [part.strip().strip("[]") for part in table.split(".") if part.strip()]
                        if not parts:
                            raise AppError("Invalid SQL Server table name.", status_code=400)
                        target = ".".join(_sqlserver_qident(part) for part in parts)
                        statement = f"UPDATE STATISTICS {target}"
                        cursor.execute(statement)
                        return {"target": table, "statement": statement}
                    statement = "EXEC sp_updatestats"
                    cursor.execute(statement)
                    return {"target": database_name, "statement": statement}

                if action == "shrink_database":
                    target_percent = int(data.target_percent or 10)
                    statement = f"DBCC SHRINKDATABASE ({_sqlserver_qident(database_name)}, {target_percent})"
                    cursor.execute(statement)
                    try:
                        cursor.fetchall()
                    except Exception:
                        pass
                    return {"target": database_name, "statement": statement, "after": {"target_free_percent": target_percent}}

                raise AppError("Unsupported SQL Server maintenance operation.", status_code=400)
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(sqlserver_error_message(exc), code="SQLSERVER_DATABASE_MAINTENANCE_FAILED", status_code=400) from exc


async def sqlserver_database_maintenance(connection: dict, data) -> dict:
    return await asyncio.to_thread(_sqlserver_maintenance_sync, connection, data)


def _mysql_qident(value: str) -> str:
    return "`" + str(value).replace("`", "``") + "`"


def _mysql_maintenance_sync(connection: dict, data) -> dict:
    action = data.action.value
    if action not in {"analyze_table", "optimize_table", "check_table"}:
        raise AppError("Unsupported MySQL/MariaDB maintenance operation.", status_code=400)
    schema = str(data.schema_name or connection.get("database") or "").strip()
    table = str(data.table_name or "").strip()
    if not schema or not table:
        raise AppError("Schema and table are required for this MySQL/MariaDB maintenance operation.", status_code=400)
    db = cursor = None
    try:
        db = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = db.cursor()
        verb = {
            "analyze_table": "ANALYZE TABLE",
            "optimize_table": "OPTIMIZE TABLE",
            "check_table": "CHECK TABLE",
        }[action]
        statement = f"{verb} {_mysql_qident(schema)}.{_mysql_qident(table)}"
        cursor.execute(statement)
        rows = cursor.fetchall()
        result_rows = [list(row) for row in rows]
        return {"target": f"{schema}.{table}", "statement": statement, "after": {"result": result_rows[-10:]}}
    except AppError:
        raise
    except MySQLError as exc:
        raise AppError(str(exc), code="MYSQL_DATABASE_MAINTENANCE_FAILED", status_code=400) from exc
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(db)


async def mysql_database_maintenance(connection: dict, data) -> dict:
    return await asyncio.to_thread(_mysql_maintenance_sync, connection, data)
