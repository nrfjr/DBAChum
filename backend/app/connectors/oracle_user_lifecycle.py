from __future__ import annotations

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.connectors.oracle_provisioning import (
    is_sensitive_reference_role,
    normalize_oracle_identifier,
    quote_oracle_identifier,
    quote_oracle_password,
)
from app.core.exceptions import AppError
from app.core.oracle_accounts import is_oracle_system_account


def _ensure_manageable_username(username: str) -> str:
    normalized = normalize_oracle_identifier(username, field_name="Username")
    if is_oracle_system_account(normalized):
        raise AppError(
            "Oracle-maintained/system accounts cannot be changed from Users & Schemas.",
            code="ORACLE_SYSTEM_ACCOUNT_PROTECTED",
            status_code=403,
        )
    return normalized


def _locked(status: str | None) -> bool:
    return "LOCKED" in (status or "").upper()


def _expired(status: str | None) -> bool:
    return "EXPIRED" in (status or "").upper()


async def get_oracle_user_lifecycle_state(connection: dict, username: str) -> dict:
    username = _ensure_manageable_username(username)

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            user_row = await oracle_connection.fetchone(
                """
                SELECT
                    username,
                    account_status,
                    default_tablespace,
                    temporary_tablespace,
                    profile,
                    created,
                    lock_date,
                    expiry_date
                FROM dba_users
                WHERE username = :username
                """,
                {"username": username},
            )
            if user_row is None:
                raise AppError(
                    "Oracle user/schema was not found.",
                    code="ORACLE_USER_NOT_FOUND",
                    status_code=404,
                )

            role_rows = await oracle_connection.fetchall(
                """
                SELECT granted_role, admin_option, default_role
                FROM dba_role_privs
                WHERE grantee = :username
                ORDER BY granted_role
                """,
                {"username": username},
            )

            warnings: list[str] = []
            try:
                privilege_rows = await oracle_connection.fetchall(
                    """
                    SELECT privilege, admin_option
                    FROM dba_sys_privs
                    WHERE grantee = :username
                    ORDER BY privilege
                    """,
                    {"username": username},
                )
            except oracledb.Error as exc:
                privilege_rows = []
                warnings.append(
                    "Direct system privilege inspection is unavailable: "
                    + oracle_error_message(exc)
                )

            try:
                try:
                    available_role_rows = await oracle_connection.fetchall(
                        "SELECT role, oracle_maintained FROM dba_roles ORDER BY role"
                    )
                    role_maintained_available = True
                except oracledb.Error:
                    available_role_rows = await oracle_connection.fetchall(
                        "SELECT role FROM dba_roles ORDER BY role"
                    )
                    role_maintained_available = False
            except oracledb.Error as exc:
                available_role_rows = []
                role_maintained_available = False
                warnings.append(
                    "Database role discovery is unavailable: "
                    + oracle_error_message(exc)
                )
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_USER_LIFECYCLE_LOOKUP_FAILED",
                status_code=400,
            ) from exc

    status = str(user_row[1] or "")
    roles = [
        {
            "name": str(row[0]),
            "admin_option": str(row[1]).upper() == "YES",
            "default_role": str(row[2]).upper() == "YES",
            "sensitive": is_sensitive_reference_role(str(row[0])),
        }
        for row in role_rows
    ]
    system_privileges = [
        {
            "name": str(row[0]),
            "admin_option": str(row[1]).upper() == "YES",
        }
        for row in privilege_rows
    ]
    available_roles = [
        {
            "name": str(row[0]),
            "sensitive": (
                is_sensitive_reference_role(str(row[0]))
                or (role_maintained_available and str(row[1]).upper() == "Y")
            ),
        }
        for row in available_role_rows
    ]

    return {
        "username": str(user_row[0]),
        "status": status,
        "locked": _locked(status),
        "expired": _expired(status),
        "default_tablespace": user_row[2],
        "temporary_tablespace": user_row[3],
        "profile": user_row[4],
        "created_at": user_row[5],
        "lock_date": user_row[6],
        "expiry_date": user_row[7],
        "roles": roles,
        "system_privileges": system_privileges,
        "available_roles": available_roles,
        "warnings": warnings,
    }


async def apply_oracle_user_access_changes(
    connection: dict,
    *,
    username: str,
    default_tablespace: str | None,
    temporary_tablespace: str | None,
    profile: str | None,
    roles: list[str],
    locked: bool,
) -> None:
    username = _ensure_manageable_username(username)
    before = await get_oracle_user_lifecycle_state(connection, username)

    resolved_default = normalize_oracle_identifier(
        default_tablespace or before["default_tablespace"],
        field_name="Default tablespace",
    )
    resolved_temp = normalize_oracle_identifier(
        temporary_tablespace or before["temporary_tablespace"],
        field_name="Temporary tablespace",
    )
    resolved_profile = normalize_oracle_identifier(
        profile or before["profile"],
        field_name="Profile",
    )
    desired_roles = {
        normalize_oracle_identifier(role, field_name="Role")
        for role in roles
    }
    current_roles = {str(item["name"]).upper() for item in before["roles"]}

    blocked_additions = sorted(
        role for role in desired_roles - current_roles if is_sensitive_reference_role(role)
    )
    if blocked_additions:
        raise AppError(
            "Sensitive roles cannot be added through this workflow: "
            + ", ".join(blocked_additions),
            code="ORACLE_SENSITIVE_ROLE_ADD_BLOCKED",
            status_code=403,
        )

    statements: list[str] = []
    if resolved_default != str(before["default_tablespace"] or "").upper():
        statements.append(
            f"ALTER USER {quote_oracle_identifier(username)} DEFAULT TABLESPACE "
            f"{quote_oracle_identifier(resolved_default)}"
        )
    if resolved_temp != str(before["temporary_tablespace"] or "").upper():
        statements.append(
            f"ALTER USER {quote_oracle_identifier(username)} TEMPORARY TABLESPACE "
            f"{quote_oracle_identifier(resolved_temp)}"
        )
    if resolved_profile != str(before["profile"] or "").upper():
        statements.append(
            f"ALTER USER {quote_oracle_identifier(username)} PROFILE "
            f"{quote_oracle_identifier(resolved_profile)}"
        )
    if bool(before["locked"]) != locked:
        statements.append(
            f"ALTER USER {quote_oracle_identifier(username)} ACCOUNT "
            + ("LOCK" if locked else "UNLOCK")
        )

    for role in sorted(desired_roles - current_roles):
        statements.append(
            f"GRANT {quote_oracle_identifier(role)} TO {quote_oracle_identifier(username)}"
        )
    for role in sorted(current_roles - desired_roles):
        statements.append(
            f"REVOKE {quote_oracle_identifier(role)} FROM {quote_oracle_identifier(username)}"
        )

    if not statements:
        return

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            for statement in statements:
                await oracle_connection.execute(statement)
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_USER_EDIT_FAILED",
                status_code=400,
            ) from exc


async def reset_oracle_user_password(
    connection: dict,
    *,
    username: str,
    password: str,
    expire_after_reset: bool = False,
) -> None:
    username = _ensure_manageable_username(username)
    password_sql = quote_oracle_password(password)

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            exists = await oracle_connection.fetchone(
                "SELECT username FROM dba_users WHERE username = :username",
                {"username": username},
            )
            if exists is None:
                raise AppError(
                    "Oracle user/schema was not found.",
                    code="ORACLE_USER_NOT_FOUND",
                    status_code=404,
                )
            await oracle_connection.execute(
                f"ALTER USER {quote_oracle_identifier(username)} IDENTIFIED BY {password_sql}"
            )
            if expire_after_reset:
                await oracle_connection.execute(
                    f"ALTER USER {quote_oracle_identifier(username)} PASSWORD EXPIRE"
                )
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_PASSWORD_RESET_FAILED",
                status_code=400,
            ) from exc


async def execute_oracle_user_account_action(
    connection: dict,
    *,
    username: str,
    action: str,
) -> None:
    username = _ensure_manageable_username(username)
    clauses = {
        "lock": "ACCOUNT LOCK",
        "unlock": "ACCOUNT UNLOCK",
        "expire_password": "PASSWORD EXPIRE",
    }
    clause = clauses.get(action)
    if clause is None:
        raise AppError(
            "Unsupported Oracle account action.",
            code="ORACLE_ACCOUNT_ACTION_INVALID",
            status_code=400,
        )

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            exists = await oracle_connection.fetchone(
                "SELECT username FROM dba_users WHERE username = :username",
                {"username": username},
            )
            if exists is None:
                raise AppError(
                    "Oracle user/schema was not found.",
                    code="ORACLE_USER_NOT_FOUND",
                    status_code=404,
                )
            await oracle_connection.execute(
                f"ALTER USER {quote_oracle_identifier(username)} {clause}"
            )
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ACCOUNT_ACTION_FAILED",
                status_code=400,
            ) from exc
