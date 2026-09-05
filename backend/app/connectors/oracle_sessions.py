from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import (
    open_oracle_connection,
    oracle_error_message,
)


LONG_RUNNING_SECONDS = 60
SESSION_LIST_LIMIT = 250


async def get_oracle_sessions(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    async with open_oracle_connection(
        connection
    ) as oracle_connection:

        try:
            try:
                major_version = int(str(oracle_connection.version).split(".", 1)[0])
            except (TypeError, ValueError):
                major_version = None

            sql_exec_start_expr = (
                "sql_exec_start"
                if major_version is not None and major_version >= 11
                else "CAST(NULL AS DATE)"
            )

            summary = await oracle_connection.fetchone(
                """
                SELECT
                    COUNT(*) AS total_sessions,

                    SUM(
                        CASE
                            WHEN status = 'ACTIVE'
                            THEN 1
                            ELSE 0
                        END
                    ) AS active_sessions,

                    SUM(
                        CASE
                            WHEN blocking_session IS NOT NULL
                            THEN 1
                            ELSE 0
                        END
                    ) AS blocked_sessions,

                    SUM(
                        CASE
                            WHEN status = 'ACTIVE'
                             AND last_call_et >= :long_running
                            THEN 1
                            ELSE 0
                        END
                    ) AS long_running_sessions

                FROM v$session

                WHERE type = 'USER'
                  AND audsid <>
                      TO_NUMBER(
                          SYS_CONTEXT(
                              'USERENV',
                              'SESSIONID'
                          )
                      )
                """,
                {
                    "long_running":
                        LONG_RUNNING_SECONDS
                },
            )

            rows = await oracle_connection.fetchall(
                f"""
                SELECT *
                FROM (
                    SELECT
                        sid,
                        serial#,
                        username,
                        status,
                        osuser,
                        machine,
                        program,
                        module,
                        sql_id,
                        {sql_exec_start_expr} AS sql_exec_start,
                        event,
                        wait_class,
                        blocking_instance,
                        blocking_session,
                        last_call_et,
                        logon_time

                    FROM v$session

                    WHERE type = 'USER'
                      AND audsid <>
                          TO_NUMBER(
                              SYS_CONTEXT(
                                  'USERENV',
                                  'SESSIONID'
                              )
                          )

                    ORDER BY
                        CASE
                            WHEN status = 'ACTIVE'
                            THEN 0
                            ELSE 1
                        END,
                        last_call_et DESC
                )

                WHERE ROWNUM <= :session_limit
                """,
                {
                    "session_limit":
                        SESSION_LIST_LIMIT
                },
            )

        except oracledb.Error as exc:
            return {
                "available": False,
                "warning":
                    oracle_error_message(exc),

                "long_running_threshold_seconds":
                    LONG_RUNNING_SECONDS,

                "checked_at": checked_at,
            }

    items = [
        {
            "sid": row[0],
            "serial_number": row[1],
            "username": row[2],
            "status": row[3],
            "os_user": row[4],
            "machine": row[5],
            "program": row[6],
            "module": row[7],
            "sql_id": row[8],
            "sql_exec_start": row[9],
            "event": row[10],
            "wait_class": row[11],
            "blocking_instance": row[12],
            "blocking_session": row[13],
            "state_seconds": row[14] or 0,
            "logon_time": row[15],
        }
        for row in rows
    ]

    return {
        "available": True,

        "total":
            int(summary[0] or 0),

        "active":
            int(summary[1] or 0),

        "blocked":
            int(summary[2] or 0),

        "long_running":
            int(summary[3] or 0),

        "long_running_threshold_seconds":
            LONG_RUNNING_SECONDS,

        "items": items,

        "checked_at": checked_at,
    }