import re
from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.core.exceptions import AppError


_PARAMETER_RE = re.compile(r"^[_A-Za-z][A-Za-z0-9_$#]*$")


def _name(value: str) -> str:
    candidate = (value or "").strip()
    if not _PARAMETER_RE.fullmatch(candidate):
        raise AppError(
            "Invalid Oracle parameter name.",
            code="ORACLE_PARAMETER_INVALID",
            status_code=400,
        )
    return candidate


def _literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


async def get_oracle_parameters(connection: dict) -> dict:
    try:
        async with open_oracle_connection(connection) as db:
            rows = await db.fetchall(
                """
                SELECT
                    name,
                    value,
                    display_value,
                    isdefault,
                    isses_modifiable,
                    issys_modifiable,
                    ismodified,
                    description
                FROM v$parameter
                ORDER BY name
                """
            )
            items = []
            for row in rows:
                items.append(
                    {
                        "name": row[0],
                        "value": None if row[1] is None else str(row[1]),
                        "display_value": None if row[2] is None else str(row[2]),
                        "dynamic": str(row[5] or "FALSE").upper() in {"IMMEDIATE", "DEFERRED"},
                        "session_modifiable": str(row[4] or "FALSE").upper() == "TRUE",
                        "system_modifiable": str(row[5] or "FALSE"),
                        "description": row[7],
                        "source": "default" if str(row[3]).upper() == "TRUE" else str(row[6] or "configured").lower(),
                    }
                )
            return {
                "scope": "instance",
                "generation": db.version,
                "available": True,
                "items": items,
                "warnings": [],
                "checked_at": datetime.now(timezone.utc),
            }
    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_PARAMETERS_FAILED",
            status_code=400,
        ) from exc


async def oracle_parameter_operation(connection: dict, data) -> dict:
    name = _name(data.name)
    try:
        async with open_oracle_connection(connection) as db:
            row = await db.fetchone(
                """
                SELECT name, value, display_value, issys_modifiable
                FROM v$parameter
                WHERE LOWER(name) = LOWER(:name)
                """,
                {"name": name},
            )
            if not row:
                raise AppError(
                    "Oracle parameter was not found or is not visible to this login.",
                    code="ORACLE_PARAMETER_NOT_FOUND",
                    status_code=404,
                )
            canonical = str(row[0])
            modifiable = str(row[3] or "FALSE").upper()
            scope = {
                "runtime": "MEMORY",
                "persistent": "SPFILE",
                "both": "BOTH",
            }[data.apply_mode]
            if scope in {"MEMORY", "BOTH"} and modifiable == "FALSE":
                raise AppError(
                    f"{canonical} is static and cannot be changed in memory. Use persistent mode and restart the instance when appropriate.",
                    code="ORACLE_PARAMETER_STATIC",
                    status_code=400,
                )

            before = {
                "name": canonical,
                "value": None if row[1] is None else str(row[1]),
                "display_value": None if row[2] is None else str(row[2]),
                "system_modifiable": modifiable,
            }
            deferred = " DEFERRED" if modifiable == "DEFERRED" and scope in {"MEMORY", "BOTH"} else ""
            statement = (
                f"ALTER SYSTEM SET {canonical} = {_literal(data.value)}"
                f"{deferred} SCOPE={scope} SID='*'"
            )
            await db.execute(statement)

            after_row = await db.fetchone(
                "SELECT value, display_value FROM v$parameter WHERE LOWER(name) = LOWER(:name)",
                {"name": canonical},
            )
            after = {
                "name": canonical,
                "value": None if not after_row or after_row[0] is None else str(after_row[0]),
                "display_value": None if not after_row or after_row[1] is None else str(after_row[1]),
                "apply_mode": data.apply_mode,
                "restart_required": scope == "SPFILE",
            }
            return {
                "target": canonical,
                "before": before,
                "after": after,
                "statement": statement,
            }
    except AppError:
        raise
    except oracledb.Error as exc:
        raise AppError(
            oracle_error_message(exc),
            code="ORACLE_PARAMETER_OPERATION_FAILED",
            status_code=400,
        ) from exc
