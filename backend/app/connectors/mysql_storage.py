from datetime import datetime, timezone

import mysql.connector.aio as mysql_aio
from mysql.connector import Error as MySQLError

from app.connectors.mysql_sessions import (
    mysql_connect_kwargs,
)
from app.core.exceptions import AppError


TABLE_LIMIT = 250


async def get_mysql_storage(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    database_name = connection.get("database")

    if not database_name:
        return {
            "available": False,
            "database_name": None,

            "data_bytes": 0,
            "index_bytes": 0,
            "total_bytes": 0,

            "tables": [],

            "warnings": [
                "A database name is required "
                "for MySQL storage monitoring."
            ],

            "checked_at": checked_at,
        }

    try:
        async with await mysql_aio.connect(
            **mysql_connect_kwargs(connection)
        ) as mysql_connection:

            async with await mysql_connection.cursor() as cursor:

                await cursor.execute(
                    """
                    SELECT
                        COALESCE(
                            SUM(DATA_LENGTH),
                            0
                        ),
                        COALESCE(
                            SUM(INDEX_LENGTH),
                            0
                        )

                    FROM information_schema.tables

                    WHERE table_schema = %s
                      AND table_type = 'BASE TABLE'
                    """,
                    (database_name,),
                )

                summary = await cursor.fetchone()

                data_bytes = int(
                    summary[0] or 0
                )

                index_bytes = int(
                    summary[1] or 0
                )

                await cursor.execute(
                    f"""
                    SELECT
                        TABLE_NAME,

                        COALESCE(DATA_LENGTH, 0),
                        COALESCE(INDEX_LENGTH, 0),

                        TABLE_ROWS

                    FROM information_schema.tables

                    WHERE table_schema = %s
                      AND table_type = 'BASE TABLE'

                    ORDER BY
                        (
                            COALESCE(
                                DATA_LENGTH,
                                0
                            )
                            +
                            COALESCE(
                                INDEX_LENGTH,
                                0
                            )
                        ) DESC

                    LIMIT {TABLE_LIMIT}
                    """,
                    (database_name,),
                )

                rows = await cursor.fetchall()

                return {
                    "available": True,

                    "database_name":
                        database_name,

                    "data_bytes":
                        data_bytes,

                    "index_bytes":
                        index_bytes,

                    "total_bytes":
                        data_bytes
                        + index_bytes,

                    "tables": [
                        {
                            "table_name":
                                row[0],

                            "data_bytes":
                                int(row[1] or 0),

                            "index_bytes":
                                int(row[2] or 0),

                            "total_bytes":
                                int(row[1] or 0)
                                + int(row[2] or 0),

                            "rows_estimate":
                                row[3],
                        }
                        for row in rows
                    ],

                    "warnings": [],
                    "checked_at": checked_at,
                }

    except MySQLError as exc:
        raise AppError(
            str(exc),
            code="MYSQL_STORAGE_FAILED",
            status_code=400,
        ) from exc