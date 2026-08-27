from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import (
    open_oracle_connection,
    oracle_error_message,
)
from app.core.oracle_accounts import is_oracle_system_account


def _is_open(status: str) -> bool:
    return status.upper() == "OPEN"


def _is_locked(status: str) -> bool:
    return "LOCKED" in status.upper()


def _is_expired(status: str) -> bool:
    return "EXPIRED" in status.upper()


BASE_USER_COLUMNS = """
    username,
    account_status,
    default_tablespace,
    temporary_tablespace,
    profile,
    created,
    lock_date,
    expiry_date
"""


async def _fetch_user_rows(oracle_connection):
    """Return every user plus whether Oracle-maintained metadata is available.

    Oracle 12c+ exposes DBA_USERS.ORACLE_MAINTAINED, which is the best source of
    truth for hiding Oracle-owned accounts. Oracle 11g and older do not expose
    that column, so fall back to the same unlimited DBA_USERS query and the
    version-neutral built-in account classifier.
    """
    try:
        rows = await oracle_connection.fetchall(
            f"""
            SELECT
                {BASE_USER_COLUMNS},
                oracle_maintained
            FROM dba_users
            ORDER BY username
            """
        )
        return rows, True
    except oracledb.Error:
        rows = await oracle_connection.fetchall(
            f"""
            SELECT
                {BASE_USER_COLUMNS}
            FROM dba_users
            ORDER BY username
            """
        )
        return rows, False


async def get_oracle_users(
    connection: dict,
) -> dict:
    checked_at = datetime.now(timezone.utc)

    async with open_oracle_connection(
        connection
    ) as oracle_connection:
        try:
            rows, has_oracle_maintained = await _fetch_user_rows(
                oracle_connection
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
        if (
            (not has_oracle_maintained or str(row[8]).upper() != "Y")
            and not is_oracle_system_account(row[0])
        )
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
