from datetime import datetime, timezone

import mysql.connector.aio as mysql_aio
from mysql.connector import Error as MySQLError

from app.connectors.mysql_processlist import (
    fetch_processlist,
)
from app.core.exceptions import AppError
from app.core.security import decrypt_secret


LONG_RUNNING_SECONDS = 60


def mysql_connect_kwargs(connection: dict):
    kwargs = {
        "host": connection["host"],
        "port": connection["port"],
        "user": connection["username"],
        "password": decrypt_secret(
            connection["password_encrypted"]
        ),
        "connection_timeout": 5,
    }

    if connection.get("database"):
        kwargs["database"] = connection["database"]

    return kwargs


async def get_mysql_sessions(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    try:
        async with await mysql_aio.connect(
            **mysql_connect_kwargs(connection)
        ) as mysql_connection:

            async with await mysql_connection.cursor() as cursor:

                rows = await fetch_processlist(cursor)

                items = [
                    {
                        "connection_id": int(row[0]),
                        "user": row[1],
                        "host": row[2],
                        "database": row[3],
                        "command": row[4],
                        "elapsed_seconds":
                            int(row[5] or 0),
                        "state": row[6],
                        "sql_text": row[7],
                    }
                    for row in rows
                ]

                total = len(items)

                active = sum(
                    1
                    for item in items
                    if item["command"] != "Sleep"
                )

                long_running = sum(
                    1
                    for item in items
                    if item["command"] != "Sleep"
                    and item["elapsed_seconds"]
                    >= LONG_RUNNING_SECONDS
                )

                blocked = None
                warnings: list[str] = []

                try:
                    await cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM information_schema.innodb_trx
                        WHERE trx_state = 'LOCK WAIT'
                        """
                    )

                    row = await cursor.fetchone()

                    blocked = int(row[0] or 0)

                except MySQLError as exc:
                    warnings.append(
                        f"Lock-wait information "
                        f"unavailable: {exc}"
                    )

                return {
                    "available": True,

                    "total": total,
                    "active": active,
                    "blocked": blocked,
                    "long_running":
                        long_running,

                    "long_running_threshold_seconds":
                        LONG_RUNNING_SECONDS,

                    "items": items,
                    "warnings": warnings,

                    "checked_at":
                        checked_at,
                }

    except MySQLError as exc:
        raise AppError(
            str(exc),
            code="MYSQL_SESSIONS_FAILED",
            status_code=400,
        ) from exc