import asyncio
from datetime import datetime, timezone

import mssql_python

from app.connectors.sqlserver import (
    _test_sqlserver_sync,
)
from app.core.exceptions import AppError
from app.core.security import decrypt_secret


LONG_RUNNING_SECONDS = 60
SESSION_LIST_LIMIT = 250


def _connect_kwargs(connection: dict):
    password = decrypt_secret(
        connection["password_encrypted"]
    )

    kwargs = {
        "server":
            f'{connection["host"]},{connection["port"]}',
        "uid": connection["username"],
        "pwd": password,
    }

    if connection.get("database"):
        kwargs["database"] = connection["database"]

    return kwargs


def _get_sqlserver_sessions_sync(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        with mssql_python.connect(
            "Encrypt=yes;TrustServerCertificate=yes;",
            timeout=5,
            autocommit=True,
            **_connect_kwargs(connection),
        ) as sql_connection:

            cursor = sql_connection.cursor()

            total = None
            active = None
            blocked = None
            long_running = None
            rows = []

            try:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM sys.dm_exec_sessions
                    WHERE is_user_process = 1
                      AND session_id <> @@SPID
                    """
                )

                total = int(
                    cursor.fetchone()[0] or 0
                )

                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*),
                        SUM(
                            CASE
                                WHEN blocking_session_id > 0
                                THEN 1 ELSE 0
                            END
                        ),
                        SUM(
                            CASE
                                WHEN DATEDIFF(
                                    SECOND,
                                    start_time,
                                    GETDATE()
                                ) >= {LONG_RUNNING_SECONDS}
                                THEN 1 ELSE 0
                            END
                        )
                    FROM sys.dm_exec_requests r
                    INNER JOIN sys.dm_exec_sessions s
                        ON s.session_id = r.session_id
                    WHERE s.is_user_process = 1
                      AND r.session_id <> @@SPID
                    """
                )

                summary = cursor.fetchone()

                active = int(summary[0] or 0)
                blocked = int(summary[1] or 0)
                long_running = int(summary[2] or 0)

            except mssql_python.Error as exc:
                warnings.append(
                    f"Session summary unavailable: {exc}"
                )

            try:
                cursor.execute(
                    f"""
                    SELECT TOP {SESSION_LIST_LIMIT}
                        s.session_id,
                        s.login_name,
                        s.status,
                        s.host_name,
                        s.program_name,

                        r.status,
                        r.command,
                        r.start_time,
                        r.total_elapsed_time,
                        r.cpu_time,
                        r.wait_type,
                        r.blocking_session_id,

                        txt.text

                    FROM sys.dm_exec_sessions s

                    LEFT JOIN sys.dm_exec_requests r
                        ON r.session_id = s.session_id

                    OUTER APPLY
                        sys.dm_exec_sql_text(
                            r.sql_handle
                        ) txt

                    WHERE s.is_user_process = 1
                      AND s.session_id <> @@SPID

                    ORDER BY
                        CASE
                            WHEN r.session_id IS NOT NULL
                            THEN 0
                            ELSE 1
                        END,
                        r.total_elapsed_time DESC
                    """
                )

                rows = cursor.fetchall()

            except mssql_python.Error as exc:
                warnings.append(
                    f"Session list unavailable: {exc}"
                )

            return {
                "available":
                    total is not None or bool(rows),

                "total": total,
                "active": active,
                "blocked": blocked,
                "long_running": long_running,

                "long_running_threshold_seconds":
                    LONG_RUNNING_SECONDS,

                "items": [
                    {
                        "session_id": row[0],
                        "login_name": row[1],
                        "status": row[2],
                        "host_name": row[3],
                        "program_name": row[4],

                        "request_status": row[5],
                        "command": row[6],
                        "request_start_time": row[7],

                        "elapsed_ms": row[8],
                        "cpu_ms": row[9],

                        "wait_type": row[10],
                        "blocking_session_id": row[11],

                        "sql_text": row[12],
                    }
                    for row in rows
                ],

                "warnings": warnings,
                "checked_at": checked_at,
            }

    except mssql_python.Error as exc:
        raise AppError(
            str(exc),
            code="SQLSERVER_SESSIONS_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_sessions(
    connection: dict,
) -> dict:
    return await asyncio.to_thread(
        _get_sqlserver_sessions_sync,
        connection,
    )