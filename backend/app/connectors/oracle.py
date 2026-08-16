import oracledb

import logging
import time

from contextlib import asynccontextmanager

from app.core.exceptions import AppError
from app.core.security import decrypt_secret

logger = logging.getLogger(__name__)


def build_oracle_params(connection: dict) -> oracledb.ConnectParams:
    kwargs = {
        "host": connection["host"],
        "port": connection["port"],
    }

    identifier_type = connection.get("oracle_identifier_type")
    identifier = connection.get("oracle_identifier")

    if identifier_type == "sid":
        kwargs["sid"] = identifier
    else:
        kwargs["service_name"] = identifier

    return oracledb.ConnectParams(**kwargs)


async def test_oracle_connection(connection: dict) -> dict:
    encrypted_password = connection.get("password_encrypted")

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    password = decrypt_secret(encrypted_password)
    params = build_oracle_params(connection)

    try:
        async with oracledb.connect_async(
            user=connection["username"],
            password=password,
            params=params,
        ) as oracle_connection:
            row = await oracle_connection.fetchone(
                """
                SELECT
                    SYS_CONTEXT('USERENV', 'DB_NAME'),
                    SYS_CONTEXT('USERENV', 'SERVICE_NAME'),
                    SYS_CONTEXT('USERENV', 'CURRENT_USER')
                FROM dual
                """
            )

            return {
                "database_name": row[0] if row else None,
                "service_name": row[1] if row else None,
                "connected_user": row[2] if row else None,
                "database_version": oracle_connection.version,
            }

    except oracledb.Error as exc:
        error = exc.args[0]

        message = getattr(
            error,
            "message",
            str(exc),
        ).strip()

        raise AppError(
            message,
            code="ORACLE_CONNECTION_FAILED",
            status_code=400,
        ) from exc
        
async def _oracle_scalar(
    oracle_connection,
    sql: str,
    metric_name: str,
    warnings: list[str],
):
    try:
        row = await oracle_connection.fetchone(sql)

        if row is None:
            return None

        return row[0]

    except oracledb.Error as exc:
        logger.warning(
            "Oracle overview metric '%s' unavailable: %s",
            metric_name,
            exc,
        )

        warnings.append(
            f"{metric_name} unavailable."
        )

        return None


async def get_oracle_overview(
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
    params = build_oracle_params(connection)

    try:
        async with oracledb.connect_async(
            user=connection["username"],
            password=password,
            params=params,
        ) as oracle_connection:
            warnings: list[str] = []

            # Lightweight round-trip measurement.
            started = time.perf_counter()

            await oracle_connection.fetchone(
                "SELECT 1 FROM dual"
            )

            response_time_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )

            identity = await oracle_connection.fetchone(
                """
                SELECT
                    SYS_CONTEXT('USERENV', 'DB_NAME'),
                    SYS_CONTEXT('USERENV', 'CON_NAME'),
                    SYS_CONTEXT('USERENV', 'SERVICE_NAME'),
                    SYS_CONTEXT('USERENV', 'INSTANCE_NAME')
                FROM dual
                """
            )

            active = await _oracle_scalar(
                oracle_connection,
                """
                SELECT COUNT(*)
                FROM v$session
                WHERE type = 'USER'
                  AND status = 'ACTIVE'
                  AND audsid <>
                      TO_NUMBER(
                          SYS_CONTEXT(
                              'USERENV',
                              'SESSIONID'
                          )
                      )
                """,
                "Active sessions",
                warnings,
            )

            connections = await _oracle_scalar(
                oracle_connection,
                """
                SELECT COUNT(*)
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
                "Connections",
                warnings,
            )

            blocked = await _oracle_scalar(
                oracle_connection,
                """
                SELECT COUNT(*)
                FROM v$session
                WHERE type = 'USER'
                  AND blocking_session_status = 'VALID'
                """,
                "Blocked sessions",
                warnings,
            )

            uptime_seconds = await _oracle_scalar(
                oracle_connection,
                """
                SELECT ROUND(
                    (SYSDATE - startup_time) * 86400
                )
                FROM v$instance
                """,
                "Uptime",
                warnings,
            )

            return {
                "response_time_ms": response_time_ms,

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
                    identity[0] if identity else None,

                "container_name":
                    identity[1] if identity else None,

                "service_name":
                    identity[2] if identity else None,

                "instance_name":
                    identity[3] if identity else None,

                "version": oracle_connection.version,

                "warnings": warnings,
            }

    except oracledb.Error as exc:
        error = exc.args[0]

        message = getattr(
            error,
            "message",
            str(exc),
        ).strip()

        raise AppError(
            message,
            code="ORACLE_MONITORING_FAILED",
            status_code=400,
        ) from exc

def oracle_error_message(exc: oracledb.Error) -> str:
    error = exc.args[0]

    return getattr(
        error,
        "message",
        str(exc),
    ).strip()


@asynccontextmanager
async def open_oracle_connection(connection: dict):
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
    params = build_oracle_params(connection)

    try:
        oracle_connection = await oracledb.connect_async(
            user=connection["username"],
            password=password,
            params=params,
        )
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_CONNECTION_FAILED",
            status_code=400,
        ) from exc

    try:
        yield oracle_connection
    finally:
        await oracle_connection.close()