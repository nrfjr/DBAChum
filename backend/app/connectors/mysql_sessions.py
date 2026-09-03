import asyncio
from datetime import datetime, timezone

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError

from app.connectors.mysql import (
    _close_mysql_resource,
    _read_mysql_identity,
    mysql_connect_kwargs,
    probe_mysql_capabilities,
)
from app.connectors.mysql_processlist import fetch_processlist
from app.core.exceptions import AppError


LONG_RUNNING_SECONDS = 60


def _blocking_map(cursor, capabilities: dict[str, bool]) -> dict[int, int]:
    if not capabilities.get("information_schema_innodb_lock_waits"):
        return {}

    try:
        cursor.execute(
            """
            SELECT
                requesting.trx_mysql_thread_id,
                blocking.trx_mysql_thread_id
            FROM information_schema.innodb_lock_waits AS waits
            JOIN information_schema.innodb_trx AS requesting
              ON requesting.trx_id = waits.requesting_trx_id
            JOIN information_schema.innodb_trx AS blocking
              ON blocking.trx_id = waits.blocking_trx_id
            """
        )
        return {
            int(row[0]): int(row[1])
            for row in cursor.fetchall()
            if row[0] is not None and row[1] is not None
        }
    except (MySQLError, TypeError, ValueError):
        return {}


def _blocked_count(cursor, capabilities: dict[str, bool]) -> int | None:
    if not capabilities.get("information_schema_innodb_trx"):
        return None

    try:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.innodb_trx
            WHERE trx_state = 'LOCK WAIT'
            """
        )
        row = cursor.fetchone()
        return int(row[0] or 0) if row else 0
    except (MySQLError, TypeError, ValueError):
        return None


def _get_mysql_sessions_sync(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    mysql_connection = None
    cursor = None

    try:
        mysql_connection = mysql_connector.connect(
            **mysql_connect_kwargs(connection)
        )
        cursor = mysql_connection.cursor()

        identity = _read_mysql_identity(cursor)
        capabilities = probe_mysql_capabilities(
            cursor,
            identity["version_info"],
        )
        database_name = connection.get("database") or None
        rows, source = fetch_processlist(
            cursor,
            capabilities,
            database_name,
        )
        blockers = _blocking_map(cursor, capabilities)

        items = [
            {
                "connection_id": int(row[0]),
                "user": row[1],
                "host": row[2],
                "database": row[3],
                "command": row[4],
                "elapsed_seconds": int(row[5] or 0),
                "state": row[6],
                "blocking_connection_id": blockers.get(int(row[0])),
                "sql_text": row[7],
            }
            for row in rows
        ]

        total = len(items)
        active = sum(
            1
            for item in items
            if str(item["command"] or "").lower() != "sleep"
        )
        long_running = sum(
            1
            for item in items
            if str(item["command"] or "").lower() != "sleep"
            and item["elapsed_seconds"] >= LONG_RUNNING_SECONDS
        )

        blocked = len(blockers) if blockers else _blocked_count(
            cursor,
            capabilities,
        )
        warnings: list[str] = []

        if not capabilities.get("performance_schema"):
            warnings.append(
                "Performance Schema is disabled or unavailable; session "
                "monitoring is using compatible processlist fallbacks."
            )
        elif source != "performance_schema.processlist":
            warnings.append(
                "Performance Schema is enabled, but its processlist table is "
                "not exposed by this server/login; INFORMATION_SCHEMA is in use."
            )

        if blocked is None:
            warnings.append(
                "InnoDB lock-wait counts are unavailable to this server/login."
            )

        return {
            "available": True,
            "database_name": database_name,
            "scope": "database" if database_name else "instance",
            "processlist_source": source,
            "performance_schema_enabled": bool(
                capabilities.get("performance_schema")
            ),
            "total": total,
            "active": active,
            "blocked": blocked,
            "long_running": long_running,
            "long_running_threshold_seconds": LONG_RUNNING_SECONDS,
            "items": items,
            "warnings": warnings,
            "checked_at": checked_at,
        }
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(mysql_connection)


async def get_mysql_sessions(connection: dict) -> dict:
    try:
        return await asyncio.to_thread(
            _get_mysql_sessions_sync,
            connection,
        )
    except AppError:
        raise
    except (MySQLError, TypeError, ValueError, OSError) as exc:
        raise AppError(
            str(exc),
            code="MYSQL_SESSIONS_FAILED",
            status_code=400,
        ) from exc
