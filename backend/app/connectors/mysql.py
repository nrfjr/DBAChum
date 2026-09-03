import asyncio
import logging
import time

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError

from app.connectors.mysql_compat import mysql_capabilities, parse_mysql_version
from app.core.exceptions import AppError
from app.core.security import decrypt_secret

logger = logging.getLogger(__name__)


def mysql_connect_kwargs(connection: dict) -> dict:
    encrypted_password = connection.get("password_encrypted")

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    kwargs = {
        "host": connection["host"],
        "port": connection["port"],
        "user": connection["username"],
        "password": decrypt_secret(encrypted_password),
        "connection_timeout": 5,
        "autocommit": True,
    }

    if connection.get("database"):
        kwargs["database"] = connection["database"]

    return kwargs


def _mysql_status_value(
    cursor,
    variable_name: str,
    metric_name: str,
    warnings: list[str],
):
    try:
        cursor.execute(f"SHOW GLOBAL STATUS LIKE '{variable_name}'")
        row = cursor.fetchone()
        if row is None:
            return None
        return int(row[1])
    except (MySQLError, TypeError, ValueError) as exc:
        logger.warning(
            "MySQL status metric '%s' unavailable: %s",
            metric_name,
            exc,
        )
        warnings.append(f"{metric_name} unavailable.")
        return None


def _mysql_variable_value(
    cursor,
    variable_name: str,
    metric_name: str,
    warnings: list[str],
):
    try:
        cursor.execute(f"SHOW GLOBAL VARIABLES LIKE '{variable_name}'")
        row = cursor.fetchone()
        if row is None:
            return None
        return row[1]
    except MySQLError as exc:
        logger.warning(
            "MySQL variable '%s' unavailable: %s",
            metric_name,
            exc,
        )
        warnings.append(f"{metric_name} unavailable.")
        return None


def _mysql_scalar(
    cursor,
    sql: str,
    metric_name: str,
    warnings: list[str],
):
    try:
        cursor.execute(sql)
        row = cursor.fetchone()
        if row is None:
            return None
        return row[0]
    except MySQLError as exc:
        logger.warning(
            "MySQL overview metric '%s' unavailable: %s",
            metric_name,
            exc,
        )
        warnings.append(f"{metric_name} unavailable.")
        return None


def _schema_object_exists(
    cursor,
    schema_name: str,
    object_name: str,
) -> bool:
    try:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE LOWER(table_schema) = LOWER(%s)
              AND LOWER(table_name) = LOWER(%s)
            """,
            (schema_name, object_name),
        )
        row = cursor.fetchone()
        return bool(row and int(row[0] or 0) > 0)
    except MySQLError:
        return False


def _schema_exists(cursor, schema_name: str) -> bool:
    try:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.schemata
            WHERE LOWER(schema_name) = LOWER(%s)
            """,
            (schema_name,),
        )
        row = cursor.fetchone()
        return bool(row and int(row[0] or 0) > 0)
    except MySQLError:
        return False


def probe_mysql_capabilities(
    cursor,
    version_info,
) -> dict[str, bool]:
    """Refine version hints with what the connected server really exposes."""
    capabilities = mysql_capabilities(version_info)

    performance_schema_value = None
    try:
        cursor.execute("SHOW GLOBAL VARIABLES LIKE 'performance_schema'")
        row = cursor.fetchone()
        performance_schema_value = row[1] if row else None
    except MySQLError:
        pass

    performance_schema_present = _schema_exists(
        cursor,
        "performance_schema",
    )
    performance_schema_enabled = str(
        performance_schema_value or ""
    ).strip().upper() in {"ON", "1", "YES", "TRUE"}

    capabilities["performance_schema_present"] = performance_schema_present
    capabilities["performance_schema_enabled"] = performance_schema_enabled
    capabilities["performance_schema"] = (
        performance_schema_present and performance_schema_enabled
    )

    capabilities["information_schema_innodb_trx"] = _schema_object_exists(
        cursor,
        "information_schema",
        "innodb_trx",
    )
    capabilities["information_schema_innodb_lock_waits"] = _schema_object_exists(
        cursor,
        "information_schema",
        "innodb_lock_waits",
    )

    # Performance Schema feature presence is runtime-probed rather than inferred
    # from version alone. MySQL/MariaDB installations can ship the schema while
    # leaving the instrumentation disabled, as seen on common XAMPP builds.
    capabilities["performance_schema_processlist"] = bool(
        capabilities["performance_schema"]
        and _schema_object_exists(cursor, "performance_schema", "processlist")
    )
    capabilities["performance_schema_threads"] = bool(
        capabilities["performance_schema"]
        and _schema_object_exists(cursor, "performance_schema", "threads")
    )
    capabilities["performance_schema_events_waits_current"] = bool(
        capabilities["performance_schema"]
        and _schema_object_exists(
            cursor,
            "performance_schema",
            "events_waits_current",
        )
    )

    if version_info.mariadb:
        detected_global_priv = _schema_object_exists(
            cursor,
            "mysql",
            "global_priv",
        )
        capabilities["mariadb_global_priv"] = (
            detected_global_priv
            or capabilities.get("mariadb_global_priv", False)
        )

    return capabilities


def _read_mysql_identity(cursor) -> dict:
    cursor.execute(
        """
        SELECT
            DATABASE(),
            CURRENT_USER(),
            VERSION(),
            @@version_comment,
            @@hostname,
            @@port
        """
    )
    row = cursor.fetchone()
    version_info = parse_mysql_version(row[2] if row else None)

    return {
        "database_name": row[0] if row else None,
        "connected_user": row[1] if row else None,
        "version_info": version_info,
        "version_comment": row[3] if row else None,
        "server_hostname": row[4] if row else None,
        "server_port": int(row[5]) if row and row[5] is not None else None,
    }


def _close_mysql_resource(resource) -> None:
    if resource is None:
        return
    try:
        resource.close()
    except Exception:
        logger.debug("Ignoring MySQL resource close failure", exc_info=True)


def _test_mysql_connection_sync(connection: dict) -> dict:
    mysql_connection = None
    cursor = None
    try:
        mysql_connection = mysql_connector.connect(
            **mysql_connect_kwargs(connection)
        )
        cursor = mysql_connection.cursor()

        identity = _read_mysql_identity(cursor)
        version_info = identity["version_info"]
        capabilities = probe_mysql_capabilities(cursor, version_info)

        return {
            "database_name": identity["database_name"],
            "connected_user": identity["connected_user"],
            "database_version": version_info.raw,
            "database_product": version_info.product_name,
            "database_generation": version_info.generation,
            "version_comment": identity["version_comment"],
            "server_hostname": identity["server_hostname"],
            "server_port": identity["server_port"],
            "service_name": None,
            "capabilities": capabilities,
        }
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(mysql_connection)


async def test_mysql_connection(connection: dict) -> dict:
    try:
        # Connector/Python's aio transport can fail against older MariaDB/
        # non-TLS endpoints while inspecting socket cipher information. Use
        # the mature synchronous connector in a worker thread so FastAPI's
        # event loop remains non-blocking while retaining broad compatibility.
        return await asyncio.to_thread(
            _test_mysql_connection_sync,
            connection,
        )
    except AppError:
        raise
    except (MySQLError, TypeError, ValueError, OSError) as exc:
        raise AppError(
            str(exc),
            code="MYSQL_CONNECTION_FAILED",
            status_code=400,
        ) from exc


def _get_mysql_overview_sync(connection: dict) -> dict:
    mysql_connection = None
    cursor = None
    try:
        mysql_connection = mysql_connector.connect(
            **mysql_connect_kwargs(connection)
        )
        cursor = mysql_connection.cursor()
        warnings: list[str] = []

        started = time.perf_counter()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        response_time_ms = round(
            (time.perf_counter() - started) * 1000,
            1,
        )

        identity = _read_mysql_identity(cursor)
        version_info = identity["version_info"]
        capabilities = probe_mysql_capabilities(cursor, version_info)

        threads_running = _mysql_status_value(
            cursor,
            "Threads_running",
            "Active threads",
            warnings,
        )
        threads_connected = _mysql_status_value(
            cursor,
            "Threads_connected",
            "Connections",
            warnings,
        )
        uptime_seconds = _mysql_status_value(
            cursor,
            "Uptime",
            "Uptime",
            warnings,
        )
        questions = _mysql_status_value(
            cursor,
            "Questions",
            "Questions",
            warnings,
        )
        slow_queries = _mysql_status_value(
            cursor,
            "Slow_queries",
            "Slow queries",
            warnings,
        )

        max_connections_raw = _mysql_variable_value(
            cursor,
            "max_connections",
            "Maximum connections",
            warnings,
        )
        data_directory = _mysql_variable_value(
            cursor,
            "datadir",
            "Data directory",
            warnings,
        )

        try:
            max_connections = (
                int(max_connections_raw)
                if max_connections_raw is not None
                else None
            )
        except (TypeError, ValueError):
            max_connections = None
            warnings.append("Maximum connections unavailable.")

        database_count = _mysql_scalar(
            cursor,
            "SELECT COUNT(*) FROM information_schema.schemata",
            "Visible database count",
            warnings,
        )

        if capabilities.get("information_schema_innodb_trx"):
            blocked = _mysql_scalar(
                cursor,
                """
                SELECT COUNT(*)
                FROM information_schema.innodb_trx
                WHERE trx_state = 'LOCK WAIT'
                """,
                "Blocked transactions",
                warnings,
            )
        else:
            blocked = None
            warnings.append(
                "InnoDB transaction lock-wait metadata is not "
                "available to this connection."
            )

        # DBAChum's own connection contributes one connected/running thread,
        # so subtract it from the human-facing workload count.
        active = (
            max(threads_running - 1, 0)
            if threads_running is not None
            else None
        )
        connections = (
            max(threads_connected - 1, 0)
            if threads_connected is not None
            else None
        )

        performance_schema_enabled = capabilities.get(
            "performance_schema",
            False,
        )

        return {
            "response_time_ms": response_time_ms,
            "active": active,
            "connections": connections,
            "blocked": int(blocked) if blocked is not None else None,
            "uptime_seconds": uptime_seconds,
            "database_name": identity["database_name"],
            "container_name": None,
            "service_name": None,
            "instance_name": None,
            "version": version_info.raw,
            "generation": version_info.generation,
            "database_product": version_info.product_name,
            "version_comment": identity["version_comment"],
            "server_hostname": identity["server_hostname"],
            "server_port": identity["server_port"],
            "database_count": (
                int(database_count)
                if database_count is not None
                else None
            ),
            "max_connections": max_connections,
            "questions": questions,
            "slow_queries": slow_queries,
            "data_directory": data_directory,
            "performance_schema_enabled": performance_schema_enabled,
            "capabilities": capabilities,
            "warnings": warnings,
        }
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(mysql_connection)


async def get_mysql_overview(connection: dict) -> dict:
    try:
        return await asyncio.to_thread(
            _get_mysql_overview_sync,
            connection,
        )
    except AppError:
        raise
    except (MySQLError, TypeError, ValueError, OSError) as exc:
        raise AppError(
            str(exc),
            code="MYSQL_MONITORING_FAILED",
            status_code=400,
        ) from exc
