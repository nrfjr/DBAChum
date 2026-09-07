import asyncio
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
    sqlserver_error_message,
)
from app.core.exceptions import AppError


def _legacy_rows(cursor):
    cursor.execute("EXEC master.dbo.sp_configure")
    return cursor.fetchall()


def _parameters_sync(connection: dict) -> dict:
    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            cursor = db.cursor()
            warnings: list[str] = []
            try:
                if identity.capabilities.get("modern_catalog_views"):
                    try:
                        cursor.execute(
                            """
                            SELECT
                                name,
                                CAST(value AS varchar(128)),
                                CAST(value_in_use AS varchar(128)),
                                CAST(minimum AS varchar(128)),
                                CAST(maximum AS varchar(128)),
                                is_dynamic,
                                is_advanced,
                                description
                            FROM sys.configurations
                            ORDER BY name
                            """
                        )
                        rows = cursor.fetchall()
                        items = [
                            {
                                "name": row[0],
                                "value": row[1],
                                "display_value": row[2],
                                "configured_value": row[1],
                                "runtime_value": row[2],
                                "dynamic": bool(row[5]),
                                "advanced": bool(row[6]),
                                "description": row[7],
                                "source": "sys.configurations",
                            }
                            for row in rows
                        ]
                    except Exception as exc:
                        warnings.append(
                            "sys.configurations was unavailable; DBAChum fell back to sp_configure. "
                            f"({sqlserver_error_message(exc)})"
                        )
                        rows = _legacy_rows(cursor)
                        items = [
                            {
                                "name": row[0],
                                "value": str(row[3]),
                                "display_value": str(row[4]),
                                "configured_value": str(row[3]),
                                "runtime_value": str(row[4]),
                                "default_value": None,
                                "dynamic": None,
                                "advanced": None,
                                "description": None,
                                "source": "sp_configure",
                            }
                            for row in rows
                        ]
                else:
                    rows = _legacy_rows(cursor)
                    items = [
                        {
                            "name": row[0],
                            "value": str(row[3]),
                            "display_value": str(row[4]),
                            "configured_value": str(row[3]),
                            "runtime_value": str(row[4]),
                            "dynamic": None,
                            "advanced": None,
                            "description": None,
                            "source": "sp_configure",
                        }
                        for row in rows
                    ]
                    warnings.append(
                        "Legacy SQL Server parameter mode is using sp_configure; dynamic/restart metadata is limited."
                    )

                return {
                    "scope": "server",
                    "generation": identity.version.generation,
                    "available": True,
                    "items": items,
                    "warnings": warnings,
                    "checked_at": datetime.now(timezone.utc),
                }
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_PARAMETERS_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_parameters(connection: dict) -> dict:
    return await asyncio.to_thread(_parameters_sync, connection)


def _parse_numeric(value: str):
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise AppError(
            "SQL Server sp_configure values must be numeric.",
            code="SQLSERVER_PARAMETER_VALUE_INVALID",
            status_code=400,
        )
    if parsed == parsed.to_integral_value():
        return int(parsed)
    return float(parsed)


def _find_sp_configure_row(cursor, name: str):
    rows = _legacy_rows(cursor)
    for row in rows:
        if str(row[0]).strip().lower() == name.strip().lower():
            return row
    return None


def _parameter_operation_sync(connection: dict, data) -> dict:
    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            cursor = db.cursor()
            try:
                value = _parse_numeric(data.value)
                canonical = data.name.strip()
                advanced_changed = False

                row = None
                modern_row = False
                if identity.capabilities.get("modern_catalog_views"):
                    try:
                        cursor.execute(
                            "SELECT name, value, value_in_use, minimum, maximum, is_dynamic, is_advanced "
                            "FROM sys.configurations WHERE LOWER(name) = LOWER(?)",
                            canonical,
                        )
                        row = cursor.fetchone()
                        modern_row = row is not None
                    except Exception:
                        row = None

                if modern_row:
                    canonical = str(row[0])
                    minimum = float(row[3])
                    maximum = float(row[4])
                    if float(value) < minimum or float(value) > maximum:
                        raise AppError(
                            f"{canonical} must be between {row[3]} and {row[4]}.",
                            code="SQLSERVER_PARAMETER_RANGE_INVALID",
                            status_code=400,
                        )
                    before = {
                        "name": canonical,
                        "configured_value": str(row[1]),
                        "runtime_value": str(row[2]),
                        "dynamic": bool(row[5]),
                        "advanced": bool(row[6]),
                    }
                    if bool(row[6]):
                        cursor.execute(
                            "SELECT CAST(value_in_use AS int) FROM sys.configurations WHERE name = 'show advanced options'"
                        )
                        advanced_row = cursor.fetchone()
                        advanced_enabled = bool(advanced_row and int(advanced_row[0] or 0))
                        if not advanced_enabled:
                            cursor.execute("EXEC sp_configure 'show advanced options', 1")
                            cursor.execute("RECONFIGURE")
                            advanced_changed = True
                else:
                    # SQL Server 2000 and restricted modern logins use the legacy
                    # sp_configure result set. If the option is hidden, briefly
                    # enable advanced options to resolve it, then restore the old state.
                    advanced_state = _find_sp_configure_row(cursor, "show advanced options")
                    advanced_enabled = bool(advanced_state and int(advanced_state[4] or 0))
                    row = _find_sp_configure_row(cursor, canonical)
                    if row is None and not advanced_enabled:
                        cursor.execute("EXEC sp_configure 'show advanced options', 1")
                        cursor.execute("RECONFIGURE")
                        advanced_changed = True
                        row = _find_sp_configure_row(cursor, canonical)
                    if row is None:
                        if advanced_changed:
                            cursor.execute("EXEC sp_configure 'show advanced options', 0")
                            cursor.execute("RECONFIGURE")
                        raise AppError(
                            "SQL Server configuration option was not found.",
                            code="SQLSERVER_PARAMETER_NOT_FOUND",
                            status_code=404,
                        )
                    canonical = str(row[0])
                    minimum = float(row[1])
                    maximum = float(row[2])
                    if float(value) < minimum or float(value) > maximum:
                        if advanced_changed:
                            cursor.execute("EXEC sp_configure 'show advanced options', 0")
                            cursor.execute("RECONFIGURE")
                        raise AppError(
                            f"{canonical} must be between {row[1]} and {row[2]}.",
                            code="SQLSERVER_PARAMETER_RANGE_INVALID",
                            status_code=400,
                        )
                    before = {
                        "name": canonical,
                        "configured_value": str(row[3]),
                        "runtime_value": str(row[4]),
                        "dynamic": None,
                        "advanced": None,
                    }

                cursor.execute("EXEC sp_configure ?, ?", canonical, value)
                cursor.execute("RECONFIGURE")

                if advanced_changed:
                    cursor.execute("EXEC sp_configure 'show advanced options', 0")
                    cursor.execute("RECONFIGURE")

                after_row = None
                if modern_row:
                    cursor.execute(
                        "SELECT value, value_in_use, is_dynamic FROM sys.configurations WHERE name = ?",
                        canonical,
                    )
                    after_row = cursor.fetchone()
                    after = {
                        "name": canonical,
                        "configured_value": str(after_row[0]) if after_row else str(value),
                        "runtime_value": str(after_row[1]) if after_row else None,
                        "restart_required": bool(after_row and not bool(after_row[2]) and str(after_row[0]) != str(after_row[1])),
                    }
                else:
                    after_row = _find_sp_configure_row(cursor, canonical)
                    after = {
                        "name": canonical,
                        "configured_value": str(after_row[3]) if after_row else str(value),
                        "runtime_value": str(after_row[4]) if after_row else None,
                        "restart_required": bool(after_row and str(after_row[3]) != str(after_row[4])),
                    }

                return {
                    "target": canonical,
                    "before": before,
                    "after": after,
                    "statement": "sp_configure + RECONFIGURE",
                }
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_PARAMETER_OPERATION_FAILED",
            status_code=400,
        ) from exc


async def sqlserver_parameter_operation(connection: dict, data) -> dict:
    return await asyncio.to_thread(_parameter_operation_sync, connection, data)
