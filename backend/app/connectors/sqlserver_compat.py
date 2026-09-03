from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
from typing import Iterator

import mssql_python

from app.core.exceptions import AppError
from app.core.security import decrypt_secret

try:
    import pyodbc  # type: ignore
except ImportError:  # pragma: no cover - exercised on deployments without legacy support
    pyodbc = None


logger = logging.getLogger(__name__)


SQLSERVER_GENERATIONS = {
    (8, None): "SQL Server 2000",
    (9, None): "SQL Server 2005",
    (10, 0): "SQL Server 2008",
    (10, 50): "SQL Server 2008 R2",
    (11, None): "SQL Server 2012",
    (12, None): "SQL Server 2014",
    (13, None): "SQL Server 2016",
    (14, None): "SQL Server 2017",
    (15, None): "SQL Server 2019",
    (16, None): "SQL Server 2022",
    (17, None): "SQL Server 2025",
}


@dataclass(frozen=True)
class SqlServerVersion:
    raw: str | None
    major: int | None
    minor: int | None
    build: int | None
    revision: int | None
    generation: str


@dataclass
class SqlServerConnectionAdapter:
    raw: object
    provider: str
    driver: str | None
    encrypt: str

    def cursor(self):
        return self.raw.cursor()

    def close(self) -> None:
        self.raw.close()


@dataclass(frozen=True)
class SqlServerIdentity:
    database_name: str | None
    connected_user: str | None
    version: SqlServerVersion
    product_level: str | None
    edition: str | None
    instance_name: str | None
    version_banner: str | None
    provider: str
    driver: str | None
    encrypt: str
    capabilities: dict[str, bool]


def parse_sqlserver_version(value: object) -> SqlServerVersion:
    raw = None if value is None else str(value).strip() or None
    parts: list[int] = []

    if raw:
        for piece in raw.split(".")[:4]:
            digits = "".join(char for char in piece if char.isdigit())
            if not digits:
                break
            parts.append(int(digits))

    major = parts[0] if len(parts) >= 1 else None
    minor = parts[1] if len(parts) >= 2 else None
    build = parts[2] if len(parts) >= 3 else None
    revision = parts[3] if len(parts) >= 4 else None

    generation = "Unknown SQL Server generation"
    if major is not None:
        if major == 10:
            generation = SQLSERVER_GENERATIONS.get(
                (10, 50 if (minor or 0) >= 50 else 0),
                "SQL Server 2008 family",
            )
        else:
            generation = SQLSERVER_GENERATIONS.get(
                (major, None),
                f"SQL Server major version {major}",
            )

    return SqlServerVersion(
        raw=raw,
        major=major,
        minor=minor,
        build=build,
        revision=revision,
        generation=generation,
    )


def sqlserver_capabilities(version: SqlServerVersion) -> dict[str, bool]:
    major = version.major

    # Keep the capability map intentionally conservative. It controls query
    # selection, not marketing labels. Unknown versions fall back to the
    # legacy-safe surface until a modern capability is positively known.
    modern = major is not None and major >= 9

    return {
        "legacy_system_tables": True,
        "dm_exec": modern,
        "modern_catalog_views": modern,
        "database_files_catalog": modern,
        "live_sql_text": modern,
        "backup_history_msdb": True,
        "backup_media_history": True,
        # Operational monitoring keeps a legacy-safe core: SQLPERF LOGSPACE,
        # SQL Agent's msdb tables, and dbo.sysfiles all predate the DMV era.
        "dbcc_logspace": True,
        "sql_agent_tables": True,
        "sql_agent_activity": major is not None and major >= 9,
        "tempdb_sysfiles": True,
        "database_state_catalog": major is not None and major >= 9,
        "datediff_big": major is not None and major >= 13,
        "compression_metadata": major is not None and major >= 10,
    }


def _connection_password(connection: dict) -> str:
    encrypted_password = connection.get("password_encrypted")
    if not encrypted_password:
        raise AppError(
            "No password is stored for this connection.",
            code="CONNECTION_PASSWORD_MISSING",
            status_code=400,
        )
    return decrypt_secret(encrypted_password)


def _mssql_connect(connection: dict, password: str, encrypt: str):
    kwargs = {
        "server": f'{connection["host"]},{connection["port"]}',
        "uid": connection["username"],
        "pwd": password,
    }
    if connection.get("database"):
        kwargs["database"] = connection["database"]

    return mssql_python.connect(
        f"Encrypt={encrypt};TrustServerCertificate=yes;",
        timeout=5,
        autocommit=True,
        **kwargs,
    )


def _installed_pyodbc_drivers() -> list[str]:
    if pyodbc is None:
        return []

    try:
        installed = list(pyodbc.drivers())
    except Exception:
        return []

    preferred = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server Native Client 10.0",
        "SQL Native Client",
        "SQL Server",
    ]

    by_lower = {driver.lower(): driver for driver in installed}
    result = [
        by_lower[name.lower()]
        for name in preferred
        if name.lower() in by_lower
    ]

    # Keep other SQL Server-capable drivers as a final fallback without
    # selecting unrelated ODBC providers.
    for driver in installed:
        if "sql server" in driver.lower() and driver not in result:
            result.append(driver)

    return result


def _pyodbc_connect(
    connection: dict,
    password: str,
    driver: str,
    encrypt: str,
):
    if pyodbc is None:
        raise RuntimeError(
            "pyodbc is not installed. Install backend requirements to use "
            "the SQL Server legacy ODBC provider."
        )

    parts = [
        f"DRIVER={{{driver}}}",
        f'SERVER={connection["host"]},{connection["port"]}',
        f'UID={connection["username"]}',
        f"PWD={password}",
        "Connection Timeout=5",
    ]

    # The Windows-era "SQL Server" ODBC driver is one of the paths that
    # can still be useful for SQL Server 2000. Avoid feeding it newer driver
    # keywords when encryption is disabled; some legacy drivers reject unknown
    # attributes instead of ignoring them.
    if driver.strip().lower() == "sql server" and encrypt == "no":
        pass
    else:
        parts.append(f"Encrypt={encrypt}")
        if encrypt == "yes":
            parts.append("TrustServerCertificate=yes")
    if connection.get("database"):
        parts.append(f'DATABASE={connection["database"]}')

    return pyodbc.connect(
        ";".join(parts) + ";",
        autocommit=True,
        timeout=5,
    )


def _encrypt_attempts(connection: dict) -> list[str]:
    configured = str(connection.get("sqlserver_encrypt") or "auto").lower()
    if configured == "yes":
        return ["yes"]
    if configured == "no":
        return ["no"]
    return ["yes", "no"]


def _format_connection_errors(errors: list[str]) -> str:
    if not errors:
        return "No compatible SQL Server provider was available."
    if len(errors) <= 3:
        return " | ".join(errors)
    return " | ".join(errors[:3]) + f" | {len(errors) - 3} more attempt(s) failed."


@contextmanager
def open_sqlserver_connection(connection: dict) -> Iterator[SqlServerConnectionAdapter]:
    """Open SQL Server with a modern-first, legacy-isolated provider chain.

    `mssql-python` remains the normal path. SQL Server 2000 and other legacy
    endpoints can opt into (or auto-fall back to) an installed ODBC driver via
    pyodbc without forcing modern servers onto the legacy stack.
    """
    password = _connection_password(connection)
    provider = str(connection.get("sqlserver_provider") or "auto").lower()
    errors: list[str] = []
    adapter: SqlServerConnectionAdapter | None = None

    if provider in {"auto", "mssql_python"}:
        for encrypt in _encrypt_attempts(connection):
            try:
                raw = _mssql_connect(connection, password, encrypt)
                adapter = SqlServerConnectionAdapter(
                    raw=raw,
                    provider="mssql_python",
                    driver=None,
                    encrypt=encrypt,
                )
                break
            except Exception as exc:
                errors.append(f"mssql-python Encrypt={encrypt}: {exc}")

        if provider == "mssql_python" and adapter is None:
            raise AppError(
                _format_connection_errors(errors),
                code="SQLSERVER_CONNECTION_FAILED",
                status_code=400,
            )

    if adapter is None and provider in {"auto", "pyodbc"}:
        configured_driver = (connection.get("sqlserver_driver") or "").strip()
        drivers = [configured_driver] if configured_driver else _installed_pyodbc_drivers()

        if not drivers:
            errors.append(
                "Legacy ODBC: no SQL Server ODBC driver is installed/configured."
            )

        for driver in drivers:
            for encrypt in _encrypt_attempts(connection):
                try:
                    raw = _pyodbc_connect(
                        connection,
                        password,
                        driver,
                        encrypt,
                    )
                    adapter = SqlServerConnectionAdapter(
                        raw=raw,
                        provider="pyodbc",
                        driver=driver,
                        encrypt=encrypt,
                    )
                    break
                except Exception as exc:
                    errors.append(
                        f"ODBC {driver} Encrypt={encrypt}: {exc}"
                    )
            if adapter is not None:
                break

    if adapter is None:
        raise AppError(
            _format_connection_errors(errors),
            code="SQLSERVER_CONNECTION_FAILED",
            status_code=400,
        )

    try:
        yield adapter
    finally:
        adapter.close()


def probe_sqlserver_identity(db: SqlServerConnectionAdapter) -> SqlServerIdentity:
    cursor = db.cursor()
    try:
        cursor.execute(
            """
            SELECT
                DB_NAME(),
                SUSER_SNAME(),
                CAST(SERVERPROPERTY('ProductVersion') AS varchar(128)),
                CAST(SERVERPROPERTY('ProductLevel') AS varchar(128)),
                CAST(SERVERPROPERTY('Edition') AS varchar(256)),
                CAST(SERVERPROPERTY('InstanceName') AS varchar(128)),
                @@VERSION
            """
        )
        row = cursor.fetchone()
    finally:
        cursor.close()

    version = parse_sqlserver_version(row[2] if row else None)
    return SqlServerIdentity(
        database_name=row[0] if row else None,
        connected_user=row[1] if row else None,
        version=version,
        product_level=row[3] if row else None,
        edition=row[4] if row else None,
        instance_name=row[5] if row else None,
        version_banner=row[6] if row else None,
        provider=db.provider,
        driver=db.driver,
        encrypt=db.encrypt,
        capabilities=sqlserver_capabilities(version),
    )


def sqlserver_error_message(exc: Exception) -> str:
    return str(exc).strip() or exc.__class__.__name__
