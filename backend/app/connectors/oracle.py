import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import time
from contextlib import asynccontextmanager

import oracledb

from app.core.exceptions import AppError
from app.core.oracle_client import initialize_oracle_client
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


def build_oracle_connect_kwargs(
    connection: dict,
    password: str,
) -> dict:
    kwargs = {
        "user": connection["username"],
        "password": password,
        "params": build_oracle_params(connection),
    }

    if connection.get("oracle_auth_mode", "normal") == "sysdba":
        kwargs["mode"] = oracledb.AUTH_MODE_SYSDBA

    return kwargs


def oracle_error_message(exc: oracledb.Error) -> str:
    error = exc.args[0]

    return getattr(
        error,
        "message",
        str(exc),
    ).strip()


class OracleConnectionAdapter:
    """Async facade around one synchronous python-oracledb Thick connection.

    python-oracledb 2.5.x supports the old OCI client needed by Oracle 10g,
    but AsyncConnection is Thin-mode only in that driver generation.  Each
    adapter therefore owns a single-worker executor so the synchronous OCI
    connection is created, queried, and closed on the same worker thread while
    FastAPI's event loop remains non-blocking.
    """

    def __init__(self, connect_kwargs: dict):
        self._connect_kwargs = connect_kwargs
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="dbachum-oracle",
        )
        self._connection = None
        self.version: str | None = None

    async def _run(self, function, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            function,
            *args,
        )

    def _connect_sync(self):
        self._connection = oracledb.connect(
            **self._connect_kwargs
        )
        self.version = self._connection.version

    async def connect(self):
        await self._run(self._connect_sync)
        return self

    def _require_connection(self):
        if self._connection is None:
            raise RuntimeError("Oracle connection is not open.")
        return self._connection

    def _fetchone_sync(self, sql: str, parameters):
        connection = self._require_connection()
        with connection.cursor() as cursor:
            if parameters is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, parameters)
            return cursor.fetchone()

    async def fetchone(self, sql: str, parameters=None):
        return await self._run(
            self._fetchone_sync,
            sql,
            parameters,
        )

    def _fetchall_sync(self, sql: str, parameters):
        connection = self._require_connection()
        with connection.cursor() as cursor:
            if parameters is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, parameters)
            return cursor.fetchall()

    async def fetchall(self, sql: str, parameters=None):
        return await self._run(
            self._fetchall_sync,
            sql,
            parameters,
        )

    def _execute_sync(self, sql: str, parameters):
        connection = self._require_connection()
        with connection.cursor() as cursor:
            if parameters is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, parameters)
            return cursor.rowcount

    async def execute(self, sql: str, parameters=None):
        return await self._run(
            self._execute_sync,
            sql,
            parameters,
        )

    def _commit_sync(self):
        self._require_connection().commit()

    async def commit(self):
        await self._run(self._commit_sync)

    def _rollback_sync(self):
        self._require_connection().rollback()

    async def rollback(self):
        await self._run(self._rollback_sync)

    def _close_sync(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    async def close(self):
        try:
            await self._run(self._close_sync)
        finally:
            self._executor.shutdown(wait=True)


@asynccontextmanager
async def open_oracle_connection(connection: dict):
    """Open Oracle through the common async facade over sync OCI calls."""
    encrypted_password = connection.get("password_encrypted")

    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )

    # Idempotent. In Thick mode this loads OCI before ConnectParams/connect.
    initialize_oracle_client()

    password = decrypt_secret(encrypted_password)
    adapter = OracleConnectionAdapter(
        build_oracle_connect_kwargs(
            connection,
            password,
        )
    )

    try:
        await adapter.connect()
    except oracledb.Error as exc:
        adapter._executor.shutdown(wait=False)
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_CONNECTION_FAILED",
            status_code=400,
        ) from exc

    try:
        yield adapter
    finally:
        await adapter.close()


async def test_oracle_connection(connection: dict) -> dict:
    try:
        async with open_oracle_connection(connection) as db:
            row = await db.fetchone(
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
                "database_version": db.version,
                "oracle_auth_mode": connection.get(
                    "oracle_auth_mode",
                    "normal",
                ),
            }

    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_CONNECTION_FAILED",
            status_code=400,
        ) from exc


async def _oracle_scalar(
    db,
    sql: str,
    metric_name: str,
    warnings: list[str],
):
    try:
        row = await db.fetchone(sql)

        if row is None:
            return None

        return row[0]

    except oracledb.Error as exc:
        logger.warning(
            "Oracle overview metric '%s' unavailable: %s",
            metric_name,
            exc,
        )
        warnings.append(f"{metric_name} unavailable.")
        return None


def _oracle_major_version(version: str | None) -> int | None:
    if not version:
        return None
    try:
        return int(str(version).split(".", 1)[0])
    except (TypeError, ValueError):
        return None


async def get_oracle_overview(connection: dict) -> dict:
    try:
        async with open_oracle_connection(connection) as db:
            warnings: list[str] = []

            started = time.perf_counter()
            await db.fetchone("SELECT 1 FROM dual")
            response_time_ms = round(
                (time.perf_counter() - started) * 1000,
                1,
            )

            # CON_NAME is a multitenant-era USERENV attribute and is not
            # available on Oracle 10g/11g.  Keep the common identity query
            # legacy-safe, then read CON_NAME only on 12c+.
            identity = await db.fetchone(
                """
                SELECT
                    SYS_CONTEXT('USERENV', 'DB_NAME'),
                    SYS_CONTEXT('USERENV', 'SERVICE_NAME'),
                    SYS_CONTEXT('USERENV', 'INSTANCE_NAME')
                FROM dual
                """
            )

            container_name = None
            major_version = _oracle_major_version(db.version)
            if major_version is not None and major_version >= 12:
                container_name = await _oracle_scalar(
                    db,
                    "SELECT SYS_CONTEXT('USERENV', 'CON_NAME') FROM dual",
                    "Container name",
                    warnings,
                )

            active = await _oracle_scalar(
                db,
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
                db,
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
                db,
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
                db,
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
                "active": int(active) if active is not None else None,
                "connections": (
                    int(connections)
                    if connections is not None
                    else None
                ),
                "blocked": int(blocked) if blocked is not None else None,
                "uptime_seconds": (
                    int(uptime_seconds)
                    if uptime_seconds is not None
                    else None
                ),
                "database_name": identity[0] if identity else None,
                "container_name": container_name,
                "service_name": identity[1] if identity else None,
                "instance_name": identity[2] if identity else None,
                "version": db.version,
                "warnings": warnings,
            }

    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_MONITORING_FAILED",
            status_code=400,
        ) from exc
