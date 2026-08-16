import asyncio

import mssql_python

import logging
import time

from app.core.exceptions import AppError
from app.core.security import decrypt_secret

logger = logging.getLogger(__name__)

def _test_sqlserver_sync(connection: dict) -> dict:
    encrypted_password = connection.get("password_encrypted")

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    password = decrypt_secret(encrypted_password)

    server = f'{connection["host"]},{connection["port"]}'

    connect_kwargs = {
        "server": server,
        "uid": connection["username"],
        "pwd": password,
    }

    if connection.get("database"):
        connect_kwargs["database"] = connection["database"]

    try:
        with mssql_python.connect(
            "Encrypt=yes;TrustServerCertificate=yes;",
            timeout=5,
            autocommit=True,
            **connect_kwargs,
        ) as sql_connection:
            cursor = sql_connection.cursor()

            cursor.execute(
                """
                SELECT
                    DB_NAME(),
                    SUSER_SNAME(),
                    CAST(
                        SERVERPROPERTY('ProductVersion')
                        AS varchar(128)
                    )
                """
            )

            row = cursor.fetchone()

            return {
                "database_name": row[0] if row else None,
                "connected_user": row[1] if row else None,
                "database_version": row[2] if row else None,
                "service_name": None,
            }

    except mssql_python.Error as exc:
        raise AppError(
            str(exc),
            code="SQLSERVER_CONNECTION_FAILED",
            status_code=400,
        ) from exc


async def test_sqlserver_connection(
    connection: dict,
) -> dict:
    return await asyncio.to_thread(
        _test_sqlserver_sync,
        connection,
    )

def _sqlserver_scalar(
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

    except mssql_python.Error as exc:
        logger.warning(
            "SQL Server overview metric '%s' unavailable: %s",
            metric_name,
            exc,
        )

        warnings.append(
            f"{metric_name} unavailable."
        )

        return None


def _get_sqlserver_overview_sync(
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

    server = (
        f'{connection["host"]},'
        f'{connection["port"]}'
    )

    connect_kwargs = {
        "server": server,
        "uid": connection["username"],
        "pwd": password,
    }

    if connection.get("database"):
        connect_kwargs["database"] = connection["database"]

    try:
        with mssql_python.connect(
            "Encrypt=yes;TrustServerCertificate=yes;",
            timeout=5,
            autocommit=True,
            **connect_kwargs,
        ) as sql_connection:

            with sql_connection.cursor() as cursor:
                warnings: list[str] = []

                started = time.perf_counter()

                cursor.execute("SELECT 1")
                cursor.fetchone()

                response_time_ms = round(
                    (
                        time.perf_counter()
                        - started
                    ) * 1000,
                    1,
                )

                cursor.execute(
                    """
                    SELECT
                        DB_NAME(),
                        CAST(
                            SERVERPROPERTY(
                                'ProductVersion'
                            )
                            AS varchar(128)
                        )
                    """
                )

                identity = cursor.fetchone()

                active = _sqlserver_scalar(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM sys.dm_exec_requests r
                    INNER JOIN sys.dm_exec_sessions s
                        ON s.session_id = r.session_id
                    WHERE s.is_user_process = 1
                      AND r.session_id <> @@SPID
                    """,
                    "Active requests",
                    warnings,
                )

                connections = _sqlserver_scalar(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM sys.dm_exec_sessions
                    WHERE is_user_process = 1
                      AND session_id <> @@SPID
                    """,
                    "Connections",
                    warnings,
                )

                blocked = _sqlserver_scalar(
                    cursor,
                    """
                    SELECT COUNT(*)
                    FROM sys.dm_exec_requests r
                    INNER JOIN sys.dm_exec_sessions s
                        ON s.session_id = r.session_id
                    WHERE s.is_user_process = 1
                      AND r.session_id <> @@SPID
                      AND r.blocking_session_id > 0
                    """,
                    "Blocked requests",
                    warnings,
                )

                uptime_seconds = _sqlserver_scalar(
                    cursor,
                    """
                    SELECT DATEDIFF_BIG(
                        SECOND,
                        create_date,
                        SYSDATETIME()
                    )
                    FROM sys.databases
                    WHERE name = 'tempdb'
                    """,
                    "Uptime",
                    warnings,
                )

                return {
                    "response_time_ms":
                        response_time_ms,

                    "active":
                        int(active)
                        if active is not None
                        else None,

                    "connections":
                        int(connections)
                        if connections is not None
                        else None,

                    "blocked":
                        int(blocked)
                        if blocked is not None
                        else None,

                    "uptime_seconds":
                        int(uptime_seconds)
                        if uptime_seconds is not None
                        else None,

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

    except mssql_python.Error as exc:
        raise AppError(
            str(exc),
            code="SQLSERVER_MONITORING_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_overview(
    connection: dict,
) -> dict:
    return await asyncio.to_thread(
        _get_sqlserver_overview_sync,
        connection,
    )