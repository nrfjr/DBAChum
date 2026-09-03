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


LONG_RUNNING_SESSION_SECONDS = 60


def _status(cursor, name: str) -> int | None:
    try:
        cursor.execute(f"SHOW GLOBAL STATUS LIKE '{name}'")
        row = cursor.fetchone()
        return int(row[1]) if row and row[1] is not None else None
    except (MySQLError, TypeError, ValueError):
        return None


def _variable(cursor, name: str):
    try:
        cursor.execute(f"SHOW GLOBAL VARIABLES LIKE '{name}'")
        row = cursor.fetchone()
        return row[1] if row else None
    except MySQLError:
        return None


def _as_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_bool(value) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized in {"ON", "1", "YES", "TRUE"}:
        return True
    if normalized in {"OFF", "0", "NO", "FALSE"}:
        return False
    return None


def _percent(value: int | None, maximum: int | None) -> float | None:
    if value is None or maximum is None or maximum <= 0:
        return None
    return round((value / maximum) * 100, 2)


def _innodb_health(cursor, capabilities: dict[str, bool]) -> dict:
    blocked = None
    active_transactions = None
    oldest_transaction_seconds = None

    if capabilities.get("information_schema_innodb_trx"):
        try:
            cursor.execute(
                """
                SELECT
                    COUNT(*),
                    SUM(CASE WHEN trx_state = 'LOCK WAIT' THEN 1 ELSE 0 END),
                    TIMESTAMPDIFF(SECOND, MIN(trx_started), NOW())
                FROM information_schema.innodb_trx
                """
            )
            row = cursor.fetchone()
            if row:
                active_transactions = int(row[0] or 0)
                blocked = int(row[1] or 0)
                oldest_transaction_seconds = (
                    int(row[2]) if row[2] is not None else None
                )
        except (MySQLError, TypeError, ValueError):
            pass

    return {
        "active_transactions": active_transactions,
        "blocked_transactions": blocked,
        "oldest_transaction_seconds": oldest_transaction_seconds,
    }


def _get_mysql_health_sync(connection: dict) -> dict:
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

        max_connections = _as_int(_variable(cursor, "max_connections"))
        threads_connected = _status(cursor, "Threads_connected")
        threads_running = _status(cursor, "Threads_running")
        max_used_connections = _status(cursor, "Max_used_connections")
        slow_queries = _status(cursor, "Slow_queries")
        aborted_connects = _status(cursor, "Aborted_connects")
        aborted_clients = _status(cursor, "Aborted_clients")
        questions = _status(cursor, "Questions")
        uptime_seconds = _status(cursor, "Uptime")
        threads_created = _status(cursor, "Threads_created")
        connections_total = _status(cursor, "Connections")
        tmp_tables = _status(cursor, "Created_tmp_tables")
        tmp_disk_tables = _status(cursor, "Created_tmp_disk_tables")

        # Remove DBAChum's own connection from the current snapshot where it
        # can be identified safely. Cumulative counters remain untouched.
        connected_display = (
            max(threads_connected - 1, 0)
            if threads_connected is not None
            else None
        )
        running_display = (
            max(threads_running - 1, 0)
            if threads_running is not None
            else None
        )

        buffer_pool_size = _as_int(_variable(cursor, "innodb_buffer_pool_size"))
        buffer_pool_data = _status(cursor, "Innodb_buffer_pool_bytes_data")

        database_name = connection.get("database") or None
        rows, processlist_source = fetch_processlist(
            cursor,
            capabilities,
            database_name,
        )
        active_process_times = [
            int(row[5] or 0)
            for row in rows
            if str(row[4] or "").lower() != "sleep"
        ]
        longest_active_seconds = max(active_process_times, default=0)
        long_running_sessions = sum(
            1
            for seconds in active_process_times
            if seconds >= LONG_RUNNING_SESSION_SECONDS
        )

        innodb = _innodb_health(cursor, capabilities)
        warnings: list[str] = []

        if not capabilities.get("performance_schema"):
            warnings.append(
                "Performance Schema is disabled or unavailable. DBAChum is "
                "using SHOW GLOBAL STATUS, INFORMATION_SCHEMA, and processlist "
                "fallbacks for this server."
            )
        elif processlist_source != "performance_schema.processlist":
            warnings.append(
                "Performance Schema is enabled, but its processlist table is "
                "not exposed by this server/login; INFORMATION_SCHEMA is in use."
            )

        if innodb["blocked_transactions"] is None:
            warnings.append(
                "InnoDB transaction lock metadata is unavailable to this "
                "server/login."
            )

        long_query_time_raw = _variable(cursor, "long_query_time")
        try:
            long_query_time_seconds = (
                float(long_query_time_raw)
                if long_query_time_raw is not None
                else None
            )
        except (TypeError, ValueError):
            long_query_time_seconds = None

        return {
            "available": True,
            "database_name": database_name,
            "scope": "database" if database_name else "instance",
            "product": identity["version_info"].product_name,
            "generation": identity["version_info"].generation,
            "performance_schema_enabled": bool(
                capabilities.get("performance_schema")
            ),
            "processlist_source": processlist_source,
            "connections": {
                "current": connected_display,
                "maximum": max_connections,
                "utilization_percent": _percent(
                    connected_display,
                    max_connections,
                ),
                "max_used": max_used_connections,
                "max_used_percent": _percent(
                    max_used_connections,
                    max_connections,
                ),
                "total_since_startup": connections_total,
                "aborted_connects": aborted_connects,
                "aborted_clients": aborted_clients,
            },
            "workload": {
                "threads_running": running_display,
                "slow_queries": slow_queries,
                "questions": questions,
                "longest_active_seconds": longest_active_seconds,
                "long_running_sessions": long_running_sessions,
                "long_running_threshold_seconds": LONG_RUNNING_SESSION_SECONDS,
                "threads_created": threads_created,
            },
            "innodb": {
                **innodb,
                "buffer_pool_size_bytes": buffer_pool_size,
                "buffer_pool_data_bytes": buffer_pool_data,
                "buffer_pool_used_percent": _percent(
                    buffer_pool_data,
                    buffer_pool_size,
                ),
            },
            "temporary_tables": {
                "created": tmp_tables,
                "created_on_disk": tmp_disk_tables,
                "disk_percent": _percent(tmp_disk_tables, tmp_tables),
            },
            "server": {
                "uptime_seconds": uptime_seconds,
                "read_only": _as_bool(_variable(cursor, "read_only")),
                "slow_query_log": _as_bool(
                    _variable(cursor, "slow_query_log")
                ),
                "long_query_time_seconds": long_query_time_seconds,
            },
            "warnings": warnings,
            "checked_at": checked_at,
        }
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(mysql_connection)


async def get_mysql_health(connection: dict) -> dict:
    try:
        return await asyncio.to_thread(
            _get_mysql_health_sync,
            connection,
        )
    except AppError:
        raise
    except (MySQLError, TypeError, ValueError, OSError) as exc:
        raise AppError(
            str(exc),
            code="MYSQL_HEALTH_FAILED",
            status_code=400,
        ) from exc
