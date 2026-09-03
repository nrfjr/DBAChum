import asyncio
from datetime import datetime, timezone

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError

from app.connectors.mysql import (
    _close_mysql_resource,
    mysql_connect_kwargs,
)
from app.core.exceptions import AppError


TABLE_LIMIT = 250


def _get_mysql_storage_sync(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    database_name = connection.get("database") or None
    mysql_connection = None
    cursor = None

    try:
        mysql_connection = mysql_connector.connect(
            **mysql_connect_kwargs(connection)
        )
        cursor = mysql_connection.cursor()
        warnings: list[str] = []

        if database_name:
            schema_where = "WHERE table_schema = %s AND table_type = 'BASE TABLE'"
            schema_params: tuple[object, ...] = (database_name,)
        else:
            schema_where = "WHERE table_type = 'BASE TABLE'"
            schema_params = ()
            warnings.append(
                "No default database is configured; storage is shown across "
                "all schemas visible to this login."
            )

        cursor.execute(
            f"""
            SELECT
                COALESCE(SUM(DATA_LENGTH), 0),
                COALESCE(SUM(INDEX_LENGTH), 0),
                COUNT(*)
            FROM information_schema.tables
            {schema_where}
            """,
            schema_params,
        )
        summary = cursor.fetchone() or (0, 0, 0)
        data_bytes = int(summary[0] or 0)
        index_bytes = int(summary[1] or 0)
        table_count = int(summary[2] or 0)

        cursor.execute(
            """
            SELECT
                TABLE_SCHEMA,
                COALESCE(SUM(DATA_LENGTH), 0),
                COALESCE(SUM(INDEX_LENGTH), 0),
                COUNT(*)
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND (%s IS NULL OR TABLE_SCHEMA = %s)
            GROUP BY TABLE_SCHEMA
            ORDER BY
                COALESCE(SUM(DATA_LENGTH), 0)
                + COALESCE(SUM(INDEX_LENGTH), 0) DESC,
                TABLE_SCHEMA
            """,
            (database_name, database_name),
        )
        schema_rows = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT
                TABLE_SCHEMA,
                TABLE_NAME,
                ENGINE,
                COALESCE(DATA_LENGTH, 0),
                COALESCE(INDEX_LENGTH, 0),
                TABLE_ROWS,
                TABLE_COLLATION
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND (%s IS NULL OR TABLE_SCHEMA = %s)
            ORDER BY
                COALESCE(DATA_LENGTH, 0)
                + COALESCE(INDEX_LENGTH, 0) DESC
            LIMIT {TABLE_LIMIT}
            """,
            (database_name, database_name),
        )
        rows = cursor.fetchall()

        return {
            "available": True,
            "database_name": database_name,
            "scope": "database" if database_name else "instance",
            "data_bytes": data_bytes,
            "index_bytes": index_bytes,
            "total_bytes": data_bytes + index_bytes,
            "table_count": table_count,
            "schema_count": len(schema_rows),
            "schemas": [
                {
                    "schema_name": row[0],
                    "data_bytes": int(row[1] or 0),
                    "index_bytes": int(row[2] or 0),
                    "total_bytes": int(row[1] or 0) + int(row[2] or 0),
                    "table_count": int(row[3] or 0),
                }
                for row in schema_rows
            ],
            "tables": [
                {
                    "schema_name": row[0],
                    "table_name": row[1],
                    "engine": row[2],
                    "data_bytes": int(row[3] or 0),
                    "index_bytes": int(row[4] or 0),
                    "total_bytes": int(row[3] or 0) + int(row[4] or 0),
                    "rows_estimate": (
                        int(row[5]) if row[5] is not None else None
                    ),
                    "collation": row[6],
                }
                for row in rows
            ],
            "warnings": warnings,
            "checked_at": checked_at,
        }
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(mysql_connection)


async def get_mysql_storage(connection: dict) -> dict:
    try:
        return await asyncio.to_thread(
            _get_mysql_storage_sync,
            connection,
        )
    except (MySQLError, TypeError, ValueError, OSError) as exc:
        raise AppError(
            str(exc),
            code="MYSQL_STORAGE_FAILED",
            status_code=400,
        ) from exc
