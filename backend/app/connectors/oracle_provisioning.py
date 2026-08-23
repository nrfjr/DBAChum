import re
from dataclasses import dataclass

import oracledb

from app.connectors.oracle import (
    open_oracle_connection,
    oracle_error_message,
)
from app.core.exceptions import AppError


ORACLE_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9_$#]{0,29}$"
)

SENSITIVE_REFERENCE_ROLES = {
    "DBA",
    "DATAPUMP_EXP_FULL_DATABASE",
    "DATAPUMP_IMP_FULL_DATABASE",
    "EXP_FULL_DATABASE",
    "IMP_FULL_DATABASE",
    "EM_EXPRESS_ALL",
    "DV_ACCTMGR",
}


@dataclass
class OracleUserProvisioningPartialError(Exception):
    message: str
    roles_applied: list[str]

    def __str__(self) -> str:
        return self.message


def normalize_oracle_identifier(
    value: str,
    *,
    field_name: str,
) -> str:
    normalized = value.strip().upper()

    if not ORACLE_IDENTIFIER_PATTERN.fullmatch(
        normalized
    ):
        raise AppError(
            f"{field_name} must be a simple Oracle identifier "
            "of 1-30 characters using letters, numbers, _, $, or #.",
            code="INVALID_ORACLE_IDENTIFIER",
            status_code=400,
        )

    return normalized


def quote_oracle_identifier(value: str) -> str:
    return f'"{value}"'


def quote_oracle_password(password: str) -> str:
    if (
        len(password) < 8
        or len(password) > 128
        or '"' in password
        or any(ord(character) < 32 for character in password)
    ):
        raise AppError(
            "Oracle password must be 8-128 characters and cannot "
            "contain double quotes or control characters.",
            code="INVALID_ORACLE_PASSWORD",
            status_code=400,
        )

    return f'"{password}"'


def is_sensitive_reference_role(role: str) -> bool:
    return role.upper() in SENSITIVE_REFERENCE_ROLES


async def oracle_user_exists(
    connection: dict,
    username: str,
) -> bool:
    username = normalize_oracle_identifier(
        username,
        field_name="Username",
    )

    async with open_oracle_connection(
        connection
    ) as oracle_connection:
        try:
            row = await oracle_connection.fetchone(
                """
                SELECT username
                FROM dba_users
                WHERE username = :username
                """,
                {"username": username},
            )
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_USER_LOOKUP_FAILED",
                status_code=400,
            ) from exc

    return row is not None


async def get_oracle_reference_user(
    connection: dict,
    username: str,
) -> dict:
    username = normalize_oracle_identifier(
        username,
        field_name="Reference username",
    )

    async with open_oracle_connection(
        connection
    ) as oracle_connection:
        try:
            user_row = await oracle_connection.fetchone(
                """
                SELECT
                    username,
                    account_status,
                    default_tablespace,
                    temporary_tablespace,
                    profile
                FROM dba_users
                WHERE username = :username
                """,
                {"username": username},
            )

            if user_row is None:
                raise AppError(
                    "Reference user was not found in this database.",
                    code="ORACLE_REFERENCE_USER_NOT_FOUND",
                    status_code=404,
                )

            role_rows = await oracle_connection.fetchall(
                """
                SELECT
                    granted_role,
                    admin_option,
                    default_role
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
                    SELECT
                        privilege,
                        admin_option
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
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_REFERENCE_USER_LOOKUP_FAILED",
                status_code=400,
            ) from exc

    roles = [
        {
            "name": row[0],
            "admin_option": str(row[1]).upper() == "YES",
            "default_role": str(row[2]).upper() == "YES",
            "sensitive": is_sensitive_reference_role(row[0]),
        }
        for row in role_rows
    ]

    system_privileges = [
        {
            "name": row[0],
            "admin_option": str(row[1]).upper() == "YES",
        }
        for row in privilege_rows
    ]

    return {
        "username": user_row[0],
        "status": user_row[1],
        "default_tablespace": user_row[2],
        "temporary_tablespace": user_row[3],
        "profile": user_row[4],
        "roles": roles,
        "system_privileges": system_privileges,
        "warnings": warnings,
    }


async def create_oracle_user(
    connection: dict,
    *,
    username: str,
    password: str,
    roles: list[str],
    default_tablespace: str | None = None,
    temporary_tablespace: str | None = None,
    profile: str | None = None,
) -> dict:
    username = normalize_oracle_identifier(
        username,
        field_name="Username",
    )

    password_sql = quote_oracle_password(password)

    normalized_roles = [
        normalize_oracle_identifier(
            role,
            field_name="Role",
        )
        for role in roles
    ]

    normalized_default_tablespace = (
        normalize_oracle_identifier(
            default_tablespace,
            field_name="Default tablespace",
        )
        if default_tablespace
        else None
    )

    normalized_temporary_tablespace = (
        normalize_oracle_identifier(
            temporary_tablespace,
            field_name="Temporary tablespace",
        )
        if temporary_tablespace
        else None
    )

    normalized_profile = (
        normalize_oracle_identifier(
            profile,
            field_name="Profile",
        )
        if profile
        else None
    )

    create_parts = [
        "CREATE USER",
        quote_oracle_identifier(username),
        "IDENTIFIED BY",
        password_sql,
    ]

    if normalized_default_tablespace:
        create_parts.extend(
            [
                "DEFAULT TABLESPACE",
                quote_oracle_identifier(
                    normalized_default_tablespace
                ),
            ]
        )

    if normalized_temporary_tablespace:
        create_parts.extend(
            [
                "TEMPORARY TABLESPACE",
                quote_oracle_identifier(
                    normalized_temporary_tablespace
                ),
            ]
        )

    if normalized_profile:
        create_parts.extend(
            [
                "PROFILE",
                quote_oracle_identifier(
                    normalized_profile
                ),
            ]
        )

    created = False
    roles_applied: list[str] = []

    async with open_oracle_connection(
        connection
    ) as oracle_connection:
        try:
            await oracle_connection.execute(
                " ".join(create_parts)
            )
            created = True

            for role in normalized_roles:
                await oracle_connection.execute(
                    "GRANT "
                    f"{quote_oracle_identifier(role)} "
                    "TO "
                    f"{quote_oracle_identifier(username)}"
                )
                roles_applied.append(role)

        except oracledb.Error as exc:
            message = oracle_error_message(exc)

            if created:
                raise OracleUserProvisioningPartialError(
                    message=message,
                    roles_applied=roles_applied,
                ) from exc

            raise AppError(
                message,
                code="ORACLE_USER_CREATE_FAILED",
                status_code=400,
            ) from exc

    return {
        "username": username,
        "roles_applied": roles_applied,
        "default_tablespace": normalized_default_tablespace,
        "temporary_tablespace": normalized_temporary_tablespace,
        "profile": normalized_profile,
    }
