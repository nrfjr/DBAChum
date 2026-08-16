from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import (
    open_oracle_connection,
    oracle_error_message,
)


ACTIVE_SQL_LIMIT = 50


async def get_oracle_activity(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    async with open_oracle_connection(
        connection
    ) as oracle_connection:

        try:
            rows = await oracle_connection.fetchall(
                """
                SELECT *
                FROM (
                    SELECT
                        s.sid,
                        s.serial#,
                        s.username,
                        s.sql_id,
                        s.sql_exec_start,
                        s.last_call_et,
                        s.module,
                        s.machine,
                        s.event,
                        s.wait_class,
                        q.sql_text

                    FROM v$session s

                    LEFT JOIN v$sql q
                        ON q.sql_id = s.sql_id
                       AND q.child_number =
                           s.sql_child_number

                    WHERE s.type = 'USER'
                      AND s.status = 'ACTIVE'
                      AND s.sql_id IS NOT NULL

                      AND s.audsid <>
                          TO_NUMBER(
                              SYS_CONTEXT(
                                  'USERENV',
                                  'SESSIONID'
                              )
                          )

                    ORDER BY
                        s.last_call_et DESC
                )

                WHERE ROWNUM <= :activity_limit
                """,
                {
                    "activity_limit":
                        ACTIVE_SQL_LIMIT
                },
            )

        except oracledb.Error as exc:
            return {
                "available": False,

                "warning":
                    oracle_error_message(exc),

                "checked_at":
                    checked_at,
            }

    items = [
        {
            "sid": row[0],
            "serial_number": row[1],
            "username": row[2],
            "sql_id": row[3],
            "sql_exec_start": row[4],
            "active_seconds":
                int(row[5] or 0),
            "module": row[6],
            "machine": row[7],
            "event": row[8],
            "wait_class": row[9],
            "sql_text": row[10],
        }
        for row in rows
    ]

    return {
        "available": True,
        "items": items,
        "checked_at": checked_at,
    }