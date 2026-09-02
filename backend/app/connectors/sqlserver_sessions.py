import asyncio
from datetime import datetime, timezone

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
    sqlserver_error_message,
)
from app.core.exceptions import AppError


LONG_RUNNING_SECONDS = 60
SESSION_LIST_LIMIT = 250


def _modern_sessions(cursor) -> tuple[int, int, int, int, list]:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM sys.dm_exec_sessions
        WHERE is_user_process = 1
          AND session_id <> @@SPID
        """
    )
    total = int(cursor.fetchone()[0] or 0)

    cursor.execute(
        f"""
        SELECT
            COUNT(*),
            SUM(CASE WHEN blocking_session_id > 0 THEN 1 ELSE 0 END),
            SUM(CASE
                    WHEN total_elapsed_time >= {LONG_RUNNING_SECONDS * 1000}
                    THEN 1 ELSE 0 END)
        FROM sys.dm_exec_requests r
        INNER JOIN sys.dm_exec_sessions s
            ON s.session_id = r.session_id
        WHERE s.is_user_process = 1
          AND r.session_id <> @@SPID
        """
    )
    counters = cursor.fetchone()
    active = int(counters[0] or 0) if counters else 0
    blocked = int(counters[1] or 0) if counters else 0
    long_running = int(counters[2] or 0) if counters else 0

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
        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) txt
        WHERE s.is_user_process = 1
          AND s.session_id <> @@SPID
        ORDER BY
            CASE WHEN r.session_id IS NOT NULL THEN 0 ELSE 1 END,
            r.total_elapsed_time DESC
        """
    )
    return total, active, blocked, long_running, cursor.fetchall()


def _legacy_sessions(cursor) -> tuple[int, int, int, int, list]:
    active_condition = (
        "status NOT IN ('sleeping', 'background', 'dormant')"
    )
    cursor.execute(
        f"""
        SELECT
            SUM(CASE WHEN spid <> @@SPID AND spid > 50 THEN 1 ELSE 0 END),
            SUM(CASE WHEN spid <> @@SPID AND spid > 50 AND {active_condition}
                     THEN 1 ELSE 0 END),
            SUM(CASE WHEN spid <> @@SPID AND spid > 50 AND blocked <> 0
                     THEN 1 ELSE 0 END),
            SUM(CASE WHEN spid <> @@SPID AND spid > 50
                          AND {active_condition}
                          AND DATEDIFF(SECOND, last_batch, GETDATE()) >= {LONG_RUNNING_SECONDS}
                     THEN 1 ELSE 0 END)
        FROM master.dbo.sysprocesses
        """
    )
    counters = cursor.fetchone()

    cursor.execute(
        f"""
        SELECT TOP {SESSION_LIST_LIMIT}
            spid,
            loginame,
            status,
            hostname,
            program_name,
            status,
            cmd,
            last_batch,
            CAST(DATEDIFF(SECOND, last_batch, GETDATE()) AS bigint) * 1000,
            cpu,
            lastwaittype,
            blocked,
            NULL
        FROM master.dbo.sysprocesses
        WHERE spid <> @@SPID
          AND spid > 50
        ORDER BY
            CASE WHEN {active_condition} THEN 0 ELSE 1 END,
            last_batch
        """
    )

    return (
        int(counters[0] or 0) if counters else 0,
        int(counters[1] or 0) if counters else 0,
        int(counters[2] or 0) if counters else 0,
        int(counters[3] or 0) if counters else 0,
        cursor.fetchall(),
    )


def _get_sqlserver_sessions_sync(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            cursor = db.cursor()
            try:
                if identity.capabilities["dm_exec"]:
                    total, active, blocked, long_running, rows = _modern_sessions(cursor)
                else:
                    total, active, blocked, long_running, rows = _legacy_sessions(cursor)
                    warnings.append(
                        "Legacy SQL Server session mode: elapsed time is based "
                        "on last_batch and live SQL text is unavailable."
                    )
            finally:
                cursor.close()

            return {
                "available": True,
                "total": total,
                "active": active,
                "blocked": blocked,
                "long_running": long_running,
                "long_running_threshold_seconds": LONG_RUNNING_SECONDS,
                "items": [
                    {
                        "session_id": int(row[0]),
                        "login_name": row[1],
                        "status": row[2],
                        "host_name": row[3],
                        "program_name": row[4],
                        "request_status": row[5],
                        "command": row[6],
                        "request_start_time": row[7],
                        "elapsed_ms": int(row[8]) if row[8] is not None else None,
                        "cpu_ms": int(row[9]) if row[9] is not None else None,
                        "wait_type": row[10],
                        "blocking_session_id": (
                            int(row[11]) if row[11] not in (None, 0) else None
                        ),
                        "sql_text": row[12],
                    }
                    for row in rows
                ],
                "warnings": warnings,
                "checked_at": checked_at,
            }

    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_SESSIONS_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_sessions(connection: dict) -> dict:
    return await asyncio.to_thread(_get_sqlserver_sessions_sync, connection)
