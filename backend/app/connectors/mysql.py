import logging
import time

import mysql.connector.aio as mysql_aio
from mysql.connector import Error as MySQLError

from app.core.exceptions import AppError
from app.core.security import decrypt_secret

logger = logging.getLogger(__name__)

async def test_mysql_connection(
    connection: dict,
) -> dict:
    encrypted_password = connection.get("password_encrypted")

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    password = decrypt_secret(encrypted_password)

    connect_kwargs = {
        "host": connection["host"],
        "port": connection["port"],
        "user": connection["username"],
        "password": password,
        "connection_timeout": 5,
    }

    if connection.get("database"):
        connect_kwargs["database"] = connection["database"]

    try:
        async with await mysql_aio.connect(
            **connect_kwargs
        ) as mysql_connection:
            async with await mysql_connection.cursor() as cursor:
                await cursor.execute(
                    """
                    SELECT
                        DATABASE(),
                        CURRENT_USER(),
                        VERSION()
                    """
                )

                row = await cursor.fetchone()

                return {
                    "database_name": row[0] if row else None,
                    "connected_user": row[1] if row else None,
                    "database_version": row[2] if row else None,
                    "service_name": None,
                }

    except MySQLError as exc:
        raise AppError(
            str(exc),
            code="MYSQL_CONNECTION_FAILED",
            status_code=400,
        ) from exc
        
async def _mysql_scalar(
    cursor,
    sql: str,
    metric_name: str,
    warnings: list[str],
):
    try:
        await cursor.execute(sql)
        row = await cursor.fetchone()

        if row is None:
            return None

        return row[0]

    except MySQLError as exc:
        logger.warning(
            "MySQL overview metric '%s' unavailable: %s",
            metric_name,
            exc,
        )

        warnings.append(
            f"{metric_name} unavailable."
        )

        return None


async def _mysql_status_value(
    cursor,
    variable_name: str,
    metric_name: str,
    warnings: list[str],
):
    try:
        await cursor.execute(
            f"""
            SHOW GLOBAL STATUS
            LIKE '{variable_name}'
            """
        )

        row = await cursor.fetchone()

        if row is None:
            return None

        return int(row[1])

    except (MySQLError, ValueError) as exc:
        logger.warning(
            "MySQL status metric '%s' unavailable: %s",
            metric_name,
            exc,
        )

        warnings.append(
            f"{metric_name} unavailable."
        )

        return None


async def get_mysql_overview(
    connection: dict,
) -> dict:
    encrypted_password = connection.get(
        "password_encrypted"
    )

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    password = decrypt_secret(encrypted_password)

    connect_kwargs = {
        "host": connection["host"],
        "port": connection["port"],
        "user": connection["username"],
        "password": password,
        "connection_timeout": 5,
    }

    if connection.get("database"):
        connect_kwargs["database"] = connection["database"]

    try:
        async with await mysql_aio.connect(
            **connect_kwargs
        ) as mysql_connection:

            async with await mysql_connection.cursor() as cursor:
                warnings: list[str] = []

                started = time.perf_counter()

                await cursor.execute("SELECT 1")
                await cursor.fetchone()

                response_time_ms = round(
                    (
                        time.perf_counter()
                        - started
                    ) * 1000,
                    1,
                )

                await cursor.execute(
                    """
                    SELECT
                        DATABASE(),
                        VERSION()
                    """
                )

                identity = await cursor.fetchone()

                threads_running = (
                    await _mysql_status_value(
                        cursor,
                        "Threads_running",
                        "Active threads",
                        warnings,
                    )
                )

                threads_connected = (
                    await _mysql_status_value(
                        cursor,
                        "Threads_connected",
                        "Connections",
                        warnings,
                    )
                )

                uptime_seconds = (
                    await _mysql_status_value(
                        cursor,
                        "Uptime",
                        "Uptime",
                        warnings,
                    )
                )

                blocked = await _mysql_scalar(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM information_schema.innodb_trx
                    WHERE trx_state = 'LOCK WAIT'
                    """,
                    "Blocked transactions",
                    warnings,
                )

                # DBAChum's own connection contributes
                # one running / connected thread.
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

                return {
                    "response_time_ms":
                        response_time_ms,

                    "active": active,
                    "connections": connections,

                    "blocked":
                        int(blocked)
                        if blocked is not None
                        else None,

                    "uptime_seconds":
                        uptime_seconds,

                    "database_name":
                        identity[0]
                        if identity
                        else None,

                    "container_name": None,
                    "service_name": None,
                    "instance_name": None,

                    "version":
                        identity[1]
                        if identity
                        else None,

                    "warnings": warnings,
                }

    except MySQLError as exc:
        raise AppError(
            str(exc),
            code="MYSQL_MONITORING_FAILED",
            status_code=400,
        ) from exc