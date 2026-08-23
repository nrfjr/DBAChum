from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import (
    open_oracle_connection,
    oracle_error_message,
)


USER_LIST_LIMIT = 1000


def _is_open(status: str) -> bool:
    return status.upper() == "OPEN"


def _is_locked(status: str) -> bool:
    return "LOCKED" in status.upper()


def _is_expired(status: str) -> bool:
    return "EXPIRED" in status.upper()


async def get_oracle_users(
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
                        username,
                        account_status,
                        default_tablespace,
                        temporary_tablespace,
                        profile,
                        created,
                        lock_date,
                        expiry_date
                    FROM dba_users
                    ORDER BY username
                )
                WHERE ROWNUM <= :user_limit
                """,
                {
                    "user_limit": USER_LIST_LIMIT,
                },
            )
        except oracledb.Error as exc:
            return {
                "available": False,
                "warning": oracle_error_message(exc),
                "checked_at": checked_at,
            }

    items = [
        {
            "username": row[0],
            "status": row[1],
            "default_tablespace": row[2],
            "temporary_tablespace": row[3],
            "profile": row[4],
            "created_at": row[5],
            "lock_date": row[6],
            "expiry_date": row[7],
        }
        for row in rows
    ]

    statuses = [
        item["status"] or ""
        for item in items
    ]

    return {
        "available": True,
        "total": len(items),
        "open": sum(
            1
            for status in statuses
            if _is_open(status)
        ),
        "locked": sum(
            1
            for status in statuses
            if _is_locked(status)
        ),
        "expired": sum(
            1
            for status in statuses
            if _is_expired(status)
        ),
        "items": items,
        "checked_at": checked_at,
    }
