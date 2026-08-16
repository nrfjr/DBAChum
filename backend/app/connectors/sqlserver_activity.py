import asyncio
from datetime import datetime, timezone

import mssql_python

from app.connectors.sqlserver_sessions import (
    _connect_kwargs,
)
from app.core.exceptions import AppError


ACTIVITY_LIMIT = 50


def _get_sqlserver_activity_sync(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    try:
        with mssql_python.connect(
            "Encrypt=yes;TrustServerCertificate=yes;",
            timeout=5,
            autocommit=True,
            **_connect_kwargs(connection),
        ) as sql_connection:

            cursor = sql_connection.cursor()

            cursor.execute(
                f"""
                SELECT TOP {ACTIVITY_LIMIT}
                    r.session_id,
                    s.login_name,
                    r.status,
                    r.command,

                    r.total_elapsed_time,
                    r.cpu_time,

                    r.wait_type,
                    r.wait_time,

                    r.blocking_session_id,

                    DB_NAME(r.database_id),

                    txt.text

                FROM sys.dm_exec_requests r

                INNER JOIN sys.dm_exec_sessions s
                    ON s.session_id = r.session_id

                OUTER APPLY
                    sys.dm_exec_sql_text(
                        r.sql_handle
                    ) txt

                WHERE s.is_user_process = 1
                  AND r.session_id <> @@SPID

                ORDER BY
                    r.total_elapsed_time DESC
                """
            )

            rows = cursor.fetchall()

            return {
                "available": True,

                "items": [
                    {
                        "session_id": row[0],
                        "login_name": row[1],
                        "status": row[2],
                        "command": row[3],

                        "elapsed_ms":
                            int(row[4] or 0),

                        "cpu_ms": row[5],

                        "wait_type": row[6],
                        "wait_ms": row[7],

                        "blocking_session_id":
                            row[8],

                        "database_name": row[9],
                        "sql_text": row[10],
                    }
                    for row in rows
                ],

                "checked_at": checked_at,
            }

    except mssql_python.Error as exc:
        return {
            "available": False,
            "warning": str(exc),
            "checked_at": checked_at,
        }


async def get_sqlserver_activity(
    connection: dict,
) -> dict:
    return await asyncio.to_thread(
        _get_sqlserver_activity_sync,
        connection,
    )