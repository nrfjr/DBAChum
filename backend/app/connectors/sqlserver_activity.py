import asyncio
from datetime import datetime, timezone

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
)


ACTIVITY_LIMIT = 50


def _get_sqlserver_activity_sync(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)

    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            cursor = db.cursor()
            try:
                if identity.capabilities["dm_exec"]:
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
                        OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) txt
                        WHERE s.is_user_process = 1
                          AND r.session_id <> @@SPID
                        ORDER BY r.total_elapsed_time DESC
                        """
                    )
                    rows = cursor.fetchall()
                    warning = None
                else:
                    cursor.execute(
                        f"""
                        SELECT TOP {ACTIVITY_LIMIT}
                            spid,
                            loginame,
                            status,
                            cmd,
                            CAST(DATEDIFF(SECOND, last_batch, GETDATE()) AS bigint) * 1000,
                            cpu,
                            lastwaittype,
                            waittime,
                            blocked,
                            DB_NAME(dbid),
                            NULL
                        FROM master.dbo.sysprocesses
                        WHERE spid <> @@SPID
                          AND spid > 50
                          AND status NOT IN ('sleeping', 'background', 'dormant')
                        ORDER BY last_batch
                        """
                    )
                    rows = cursor.fetchall()
                    warning = (
                        "Legacy SQL Server activity mode is using sysprocesses; "
                        "CPU is session-cumulative and live SQL text is unavailable."
                    )
            finally:
                cursor.close()

            return {
                "available": True,
                "items": [
                    {
                        "session_id": int(row[0]),
                        "login_name": row[1],
                        "status": row[2],
                        "command": row[3],
                        "elapsed_ms": int(row[4] or 0),
                        "cpu_ms": int(row[5]) if row[5] is not None else None,
                        "wait_type": row[6],
                        "wait_ms": int(row[7]) if row[7] is not None else None,
                        "blocking_session_id": (
                            int(row[8]) if row[8] not in (None, 0) else None
                        ),
                        "database_name": row[9],
                        "sql_text": row[10],
                    }
                    for row in rows
                ],
                "warning": warning,
                "checked_at": checked_at,
            }
    except Exception as exc:
        return {
            "available": False,
            "items": [],
            "warning": str(exc).strip() or exc.__class__.__name__,
            "checked_at": checked_at,
        }


async def get_sqlserver_activity(connection: dict) -> dict:
    return await asyncio.to_thread(_get_sqlserver_activity_sync, connection)
