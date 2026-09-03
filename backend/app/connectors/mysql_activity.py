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


ACTIVITY_LIMIT = 50


def _innodb_transactions(cursor, capabilities: dict[str, bool]) -> dict[int, dict]:
    if not capabilities.get("information_schema_innodb_trx"):
        return {}

    try:
        cursor.execute(
            """
            SELECT
                trx_mysql_thread_id,
                trx_id,
                trx_state,
                trx_started,
                trx_wait_started,
                trx_query
            FROM information_schema.innodb_trx
            """
        )
        result: dict[int, dict] = {}
        for row in cursor.fetchall():
            if row[0] is None:
                continue
            result[int(row[0])] = {
                "transaction_id": str(row[1]) if row[1] is not None else None,
                "transaction_state": row[2],
                "transaction_started": row[3],
                "transaction_wait_started": row[4],
                "transaction_query": row[5],
            }
        return result
    except MySQLError:
        return {}


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


def _performance_waits(cursor, capabilities: dict[str, bool]) -> dict[int, dict]:
    if not (
        capabilities.get("performance_schema_threads")
        and capabilities.get("performance_schema_events_waits_current")
    ):
        return {}

    try:
        cursor.execute(
            """
            SELECT
                threads.PROCESSLIST_ID,
                waits.EVENT_NAME,
                waits.OBJECT_SCHEMA,
                waits.OBJECT_NAME
            FROM performance_schema.threads AS threads
            LEFT JOIN performance_schema.events_waits_current AS waits
              ON waits.THREAD_ID = threads.THREAD_ID
            WHERE threads.PROCESSLIST_ID IS NOT NULL
            """
        )
        result: dict[int, dict] = {}
        for row in cursor.fetchall():
            if row[0] is None:
                continue
            wait_object = None
            if row[2] or row[3]:
                wait_object = ".".join(
                    str(value)
                    for value in (row[2], row[3])
                    if value
                )
            result[int(row[0])] = {
                "wait_event": row[1],
                "wait_object": wait_object,
            }
        return result
    except MySQLError:
        return {}


def _get_mysql_activity_sync(connection: dict) -> dict:
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
        transactions = _innodb_transactions(cursor, capabilities)
        blockers = _blocking_map(cursor, capabilities)
        waits = _performance_waits(cursor, capabilities)

        active_rows = [
            row
            for row in rows
            if str(row[4] or "").lower() != "sleep"
        ][:ACTIVITY_LIMIT]

        items = []
        for row in active_rows:
            connection_id = int(row[0])
            transaction = transactions.get(connection_id, {})
            wait = waits.get(connection_id, {})
            sql_text = row[7] or transaction.get("transaction_query")

            items.append(
                {
                    "connection_id": connection_id,
                    "user": row[1],
                    "host": row[2],
                    "database": row[3],
                    "command": row[4],
                    "elapsed_seconds": int(row[5] or 0),
                    "state": row[6],
                    "transaction_id": transaction.get("transaction_id"),
                    "transaction_state": transaction.get("transaction_state"),
                    "transaction_started": transaction.get("transaction_started"),
                    "transaction_wait_started": transaction.get(
                        "transaction_wait_started"
                    ),
                    "wait_event": wait.get("wait_event"),
                    "wait_object": wait.get("wait_object"),
                    "blocking_connection_id": blockers.get(connection_id),
                    "sql_text": sql_text,
                }
            )

        warnings: list[str] = []
        if not capabilities.get("performance_schema"):
            warnings.append(
                "Performance Schema is disabled or unavailable; activity is "
                "using processlist and InnoDB metadata fallbacks."
            )
        else:
            if source != "performance_schema.processlist":
                warnings.append(
                    "Performance Schema is enabled, but its processlist table is "
                    "not exposed by this server/login; INFORMATION_SCHEMA is in use."
                )
            if not (
                capabilities.get("performance_schema_threads")
                and capabilities.get("performance_schema_events_waits_current")
            ):
                warnings.append(
                    "Current Performance Schema wait-event metadata is not "
                    "available on this server/login."
                )

        return {
            "available": True,
            "database_name": database_name,
            "scope": "database" if database_name else "instance",
            "processlist_source": source,
            "performance_schema_enabled": bool(
                capabilities.get("performance_schema")
            ),
            "items": items,
            "warnings": warnings,
            "checked_at": checked_at,
        }
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(mysql_connection)


async def get_mysql_activity(connection: dict) -> dict:
    try:
        return await asyncio.to_thread(
            _get_mysql_activity_sync,
            connection,
        )
    except (MySQLError, TypeError, ValueError, OSError) as exc:
        return {
            "available": False,
            "database_name": connection.get("database") or None,
            "scope": "database" if connection.get("database") else "instance",
            "processlist_source": None,
            "performance_schema_enabled": None,
            "warning": str(exc),
            "warnings": [str(exc)],
            "items": [],
            "checked_at": datetime.now(timezone.utc),
        }
