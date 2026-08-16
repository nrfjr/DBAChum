from datetime import datetime, timezone

import mysql.connector.aio as mysql_aio
from mysql.connector import Error as MySQLError

from app.connectors.mysql_processlist import (
    fetch_processlist,
)
from app.connectors.mysql_sessions import (
    mysql_connect_kwargs,
)


ACTIVITY_LIMIT = 50


async def get_mysql_activity(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    try:
        async with await mysql_aio.connect(
            **mysql_connect_kwargs(connection)
        ) as mysql_connection:

            async with await mysql_connection.cursor() as cursor:

                rows = await fetch_processlist(cursor)

                active = [
                    row
                    for row in rows
                    if row[4] != "Sleep"
                    and row[7] is not None
                ][:ACTIVITY_LIMIT]

                return {
                    "available": True,

                    "items": [
                        {
                            "connection_id":
                                int(row[0]),

                            "user": row[1],
                            "host": row[2],
                            "database": row[3],

                            "elapsed_seconds":
                                int(row[5] or 0),

                            "state": row[6],
                            "sql_text": row[7],
                        }
                        for row in active
                    ],

                    "checked_at": checked_at,
                }

    except MySQLError as exc:
        return {
            "available": False,
            "warning": str(exc),
            "items": [],
            "checked_at": checked_at,
        }