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


async def find_existing_oracle_users(
    connection: dict,
    usernames: list[str],
) -> set[str]:
    normalized: list[str] = []
    for username in usernames:
        value = normalize_oracle_identifier(username, field_name="Username")
        if value not in normalized:
            normalized.append(value)

    if not normalized:
        return set()

    existing: set[str] = set()
    async with open_oracle_connection(connection) as oracle_connection:
        try:
            # Oracle limits IN lists; keep well below the limit and use binds.
            for offset in range(0, len(normalized), 500):
                chunk = normalized[offset:offset + 500]
                binds = {f"u{i}": value for i, value in enumerate(chunk)}
                placeholders = ", ".join(f":u{i}" for i in range(len(chunk)))
                rows = await oracle_connection.fetchall(
                    f"SELECT username FROM dba_users WHERE username IN ({placeholders})",
                    binds,
                )
                existing.update(str(row[0]).upper() for row in rows)
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_USER_LOOKUP_FAILED",
                status_code=400,
            ) from exc

    return existing




async def count_oracle_rows_by_match(
    connection: dict,
    *,
    owner: str,
    table_name: str,
    match_values: dict[str, object],
) -> int:
    owner = normalize_oracle_identifier(owner, field_name="Schema")
    table_name = normalize_oracle_identifier(table_name, field_name="Table")

    if not match_values:
        raise AppError(
            "At least one upsert match column is required.",
            code="PROVISIONING_MATCH_REQUIRED",
            status_code=400,
        )

    predicates: list[str] = []
    parameters: dict[str, object] = {}

    for index, (column_name, value) in enumerate(match_values.items()):
        column = normalize_oracle_identifier(
            column_name,
            field_name="Upsert match column",
        )
        quoted_column = quote_oracle_identifier(column)
        if value is None:
            predicates.append(f"{quoted_column} IS NULL")
        else:
            bind_name = f"match_{index}"
            predicates.append(f"{quoted_column} = :{bind_name}")
            parameters[bind_name] = value

    sql = (
        "SELECT COUNT(*) FROM "
        f"{quote_oracle_identifier(owner)}.{quote_oracle_identifier(table_name)} "
        "WHERE " + " AND ".join(predicates)
    )

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            row = await oracle_connection.fetchone(sql, parameters)
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="PROVISIONING_MATCH_LOOKUP_FAILED",
                status_code=400,
            ) from exc

    return int(row[0]) if row else 0


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


@dataclass
class OracleUserReconcilePartialError(Exception):
    message: str
    account_action: str
    roles_added: list[str]
    roles_already_present: list[str]

    def __str__(self) -> str:
        return self.message


async def reconcile_oracle_user(
    connection: dict,
    *,
    username: str,
    password: str,
    roles: list[str],
    default_tablespace: str | None = None,
    temporary_tablespace: str | None = None,
    profile: str | None = None,
) -> dict:
    """Create or reconcile one Oracle account idempotently.

    The reviewed password is applied on both CREATE and ALTER so password-mapped
    application rows stay aligned with the database account during an upsert run.
    Existing unrelated roles are preserved; only missing reviewed roles are added.
    """
    username = normalize_oracle_identifier(username, field_name="Username")
    password_sql = quote_oracle_password(password)
    normalized_roles = [
        normalize_oracle_identifier(role, field_name="Role")
        for role in roles
    ]
    normalized_default_tablespace = (
        normalize_oracle_identifier(default_tablespace, field_name="Default tablespace")
        if default_tablespace else None
    )
    normalized_temporary_tablespace = (
        normalize_oracle_identifier(temporary_tablespace, field_name="Temporary tablespace")
        if temporary_tablespace else None
    )
    normalized_profile = (
        normalize_oracle_identifier(profile, field_name="Profile")
        if profile else None
    )

    account_action = "unchanged"
    roles_added: list[str] = []
    roles_already_present: list[str] = []

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            user_row = await oracle_connection.fetchone(
                """
                SELECT username
                FROM dba_users
                WHERE username = :username
                """,
                {"username": username},
            )

            if user_row is None:
                parts = [
                    "CREATE USER",
                    quote_oracle_identifier(username),
                    "IDENTIFIED BY",
                    password_sql,
                ]
                if normalized_default_tablespace:
                    parts.extend([
                        "DEFAULT TABLESPACE",
                        quote_oracle_identifier(normalized_default_tablespace),
                    ])
                if normalized_temporary_tablespace:
                    parts.extend([
                        "TEMPORARY TABLESPACE",
                        quote_oracle_identifier(normalized_temporary_tablespace),
                    ])
                if normalized_profile:
                    parts.extend([
                        "PROFILE",
                        quote_oracle_identifier(normalized_profile),
                    ])
                await oracle_connection.execute(" ".join(parts))
                account_action = "created"
            else:
                parts = [
                    "ALTER USER",
                    quote_oracle_identifier(username),
                    "IDENTIFIED BY",
                    password_sql,
                ]
                if normalized_default_tablespace:
                    parts.extend([
                        "DEFAULT TABLESPACE",
                        quote_oracle_identifier(normalized_default_tablespace),
                    ])
                if normalized_temporary_tablespace:
                    parts.extend([
                        "TEMPORARY TABLESPACE",
                        quote_oracle_identifier(normalized_temporary_tablespace),
                    ])
                if normalized_profile:
                    parts.extend([
                        "PROFILE",
                        quote_oracle_identifier(normalized_profile),
                    ])
                await oracle_connection.execute(" ".join(parts))
                account_action = "altered"

            existing_role_rows = await oracle_connection.fetchall(
                """
                SELECT granted_role
                FROM dba_role_privs
                WHERE grantee = :username
                """,
                {"username": username},
            )
            existing_roles = {str(row[0]).upper() for row in existing_role_rows}

            for role in normalized_roles:
                if role in existing_roles:
                    roles_already_present.append(role)
                    continue
                await oracle_connection.execute(
                    "GRANT "
                    f"{quote_oracle_identifier(role)} "
                    "TO "
                    f"{quote_oracle_identifier(username)}"
                )
                roles_added.append(role)

        except oracledb.Error as exc:
            message = oracle_error_message(exc)
            if account_action != "unchanged" or roles_added:
                raise OracleUserReconcilePartialError(
                    message=message,
                    account_action=account_action,
                    roles_added=roles_added,
                    roles_already_present=roles_already_present,
                ) from exc
            raise AppError(
                message,
                code="ORACLE_USER_RECONCILE_FAILED",
                status_code=400,
            ) from exc

    return {
        "username": username,
        "account_action": account_action,
        "password_applied": True,
        "roles_added": roles_added,
        "roles_already_present": roles_already_present,
        "default_tablespace": normalized_default_tablespace,
        "temporary_tablespace": normalized_temporary_tablespace,
        "profile": normalized_profile,
    }


async def reconcile_oracle_roles(
    connection: dict,
    *,
    username: str,
    roles: list[str],
) -> dict:
    """Grant only missing reviewed roles without touching account attributes/password."""
    username = normalize_oracle_identifier(username, field_name="Username")
    normalized_roles = [
        normalize_oracle_identifier(role, field_name="Role")
        for role in roles
    ]
    roles_added: list[str] = []
    roles_already_present: list[str] = []

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            user_row = await oracle_connection.fetchone(
                "SELECT username FROM dba_users WHERE username = :username",
                {"username": username},
            )
            if user_row is None:
                raise AppError(
                    "Oracle account no longer exists; the account step must be recovered first.",
                    code="PROVISIONING_ACCOUNT_MISSING",
                    status_code=409,
                )

            existing_role_rows = await oracle_connection.fetchall(
                "SELECT granted_role FROM dba_role_privs WHERE grantee = :username",
                {"username": username},
            )
            existing_roles = {str(row[0]).upper() for row in existing_role_rows}
            for role in normalized_roles:
                if role in existing_roles:
                    roles_already_present.append(role)
                    continue
                await oracle_connection.execute(
                    "GRANT "
                    f"{quote_oracle_identifier(role)} "
                    "TO "
                    f"{quote_oracle_identifier(username)}"
                )
                roles_added.append(role)
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ROLE_RECONCILE_FAILED",
                status_code=400,
            ) from exc

    return {
        "roles_added": roles_added,
        "roles_already_present": roles_already_present,
    }


def _build_match_clause(match_values: dict[str, object]):
    predicates: list[str] = []
    parameters: dict[str, object] = {}
    for index, (column_name, value) in enumerate(match_values.items()):
        column = normalize_oracle_identifier(
            column_name,
            field_name="Upsert match column",
        )
        quoted = quote_oracle_identifier(column)
        if value is None:
            predicates.append(f"{quoted} IS NULL")
        else:
            bind_name = f"match_{index}"
            predicates.append(f"{quoted} = :{bind_name}")
            parameters[bind_name] = value
    return " AND ".join(predicates), parameters


async def fetch_oracle_provisioning_row(
    connection: dict,
    *,
    owner: str,
    table_name: str,
    match_values: dict[str, object],
    columns: list[str],
) -> dict:
    """Read one lifecycle row for conservative deprovision verification."""
    owner = normalize_oracle_identifier(owner, field_name="Schema")
    table_name = normalize_oracle_identifier(table_name, field_name="Table")
    if not match_values:
        raise AppError(
            "At least one upsert match column is required.",
            code="PROVISIONING_MATCH_REQUIRED",
            status_code=400,
        )

    normalized_columns: list[str] = []
    for column in [*match_values.keys(), *columns]:
        normalized = normalize_oracle_identifier(column, field_name="Provisioning column")
        if normalized not in normalized_columns:
            normalized_columns.append(normalized)

    match_sql, match_parameters = _build_match_clause(match_values)
    owner_sql = quote_oracle_identifier(owner)
    table_sql = quote_oracle_identifier(table_name)

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            count_row = await oracle_connection.fetchone(
                f"SELECT COUNT(*) FROM {owner_sql}.{table_sql} WHERE {match_sql}",
                match_parameters,
            )
            existing_rows = int(count_row[0]) if count_row else 0
            if existing_rows != 1:
                return {"existing_rows": existing_rows, "values": {}}

            selected = await oracle_connection.fetchone(
                "SELECT "
                + ", ".join(quote_oracle_identifier(column) for column in normalized_columns)
                + f" FROM {owner_sql}.{table_sql} WHERE {match_sql}",
                match_parameters,
            )
            values = {
                column: selected[index] if selected else None
                for index, column in enumerate(normalized_columns)
            }
            return {"existing_rows": 1, "values": values}
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="PROVISIONING_ROW_LOOKUP_FAILED",
                status_code=400,
            ) from exc


async def upsert_oracle_provisioning_row(
    connection: dict,
    *,
    owner: str,
    table_name: str,
    match_values: dict[str, object],
    insert_values: dict[str, object],
    update_values: dict[str, object],
    sequence_columns: dict[str, str],
) -> dict:
    """Execute one profile table step as an idempotent INSERT-or-UPDATE.

    Besides the action, return the non-redacted before/after row values to the
    caller. The service layer is responsible for redacting sensitive columns
    before anything is persisted in MongoDB.
    """
    owner = normalize_oracle_identifier(owner, field_name="Schema")
    table_name = normalize_oracle_identifier(table_name, field_name="Table")
    if not match_values:
        raise AppError(
            "At least one upsert match column is required.",
            code="PROVISIONING_MATCH_REQUIRED",
            status_code=400,
        )

    for column, value in match_values.items():
        normalize_oracle_identifier(column, field_name="Upsert match column")
        if value is None or (isinstance(value, str) and not value.strip()):
            raise AppError(
                f'Upsert match value for "{column}" is required.',
                code="PROVISIONING_MATCH_VALUE_REQUIRED",
                status_code=400,
            )

    owner_sql = quote_oracle_identifier(owner)
    table_sql = quote_oracle_identifier(table_name)
    match_sql, match_parameters = _build_match_clause(match_values)

    tracked_columns: list[str] = []
    for column in [*match_values.keys(), *insert_values.keys(), *update_values.keys(), *sequence_columns.keys()]:
        normalized = normalize_oracle_identifier(column, field_name="Provisioning column")
        if normalized not in tracked_columns:
            tracked_columns.append(normalized)

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            row = await oracle_connection.fetchone(
                f"SELECT COUNT(*) FROM {owner_sql}.{table_sql} WHERE {match_sql}",
                match_parameters,
            )
            existing_rows = int(row[0]) if row else 0

            if existing_rows > 1:
                raise AppError(
                    f"Upsert matched {existing_rows} rows; duplicate identity must be resolved before provisioning can continue.",
                    code="PROVISIONING_UPSERT_CONFLICT",
                    status_code=409,
                )

            before_values: dict[str, object] = {}
            if existing_rows == 1 and tracked_columns:
                selected = await oracle_connection.fetchone(
                    "SELECT "
                    + ", ".join(quote_oracle_identifier(column) for column in tracked_columns)
                    + f" FROM {owner_sql}.{table_sql} WHERE {match_sql}",
                    match_parameters,
                )
                before_values = {
                    column: selected[index] if selected else None
                    for index, column in enumerate(tracked_columns)
                }

            if existing_rows == 0:
                resolved_insert = dict(insert_values)
                generated_values: dict[str, object] = {}
                for column_name, sequence_name in sequence_columns.items():
                    column = normalize_oracle_identifier(
                        column_name,
                        field_name="Provisioning column",
                    )
                    sequence = normalize_oracle_identifier(
                        sequence_name,
                        field_name="Oracle sequence",
                    )
                    seq_row = await oracle_connection.fetchone(
                        "SELECT "
                        f"{owner_sql}.{quote_oracle_identifier(sequence)}.NEXTVAL "
                        "FROM dual"
                    )
                    sequence_value = seq_row[0] if seq_row else None
                    resolved_insert[column] = sequence_value
                    generated_values[column] = sequence_value

                if not resolved_insert:
                    raise AppError(
                        "Provisioning table step has no insertable columns.",
                        code="PROVISIONING_INSERT_VALUES_REQUIRED",
                        status_code=400,
                    )

                columns = [
                    normalize_oracle_identifier(column, field_name="Provisioning column")
                    for column in resolved_insert
                ]
                bind_names = [f"value_{index}" for index in range(len(columns))]
                params = {
                    bind_name: resolved_insert[column]
                    for bind_name, column in zip(bind_names, columns)
                }
                sql = (
                    f"INSERT INTO {owner_sql}.{table_sql} ("
                    + ", ".join(quote_oracle_identifier(column) for column in columns)
                    + ") VALUES ("
                    + ", ".join(f":{bind_name}" for bind_name in bind_names)
                    + ")"
                )
                rowcount = await oracle_connection.execute(sql, params)
                await oracle_connection.commit()
                return {
                    "action": "inserted",
                    "existing_rows": 0,
                    "rowcount": rowcount,
                    "generated_values": generated_values,
                    "before_values": {},
                    "after_values": resolved_insert,
                }

            safe_update_values = {
                normalize_oracle_identifier(column, field_name="Provisioning column"): value
                for column, value in update_values.items()
                if column.upper() not in {key.upper() for key in match_values}
            }
            if not safe_update_values:
                return {
                    "action": "unchanged",
                    "existing_rows": 1,
                    "rowcount": 0,
                    "generated_values": {},
                    "before_values": before_values,
                    "after_values": dict(before_values),
                }

            set_parts: list[str] = []
            params = dict(match_parameters)
            for index, (column, value) in enumerate(safe_update_values.items()):
                bind_name = f"set_{index}"
                set_parts.append(f"{quote_oracle_identifier(column)} = :{bind_name}")
                params[bind_name] = value

            rowcount = await oracle_connection.execute(
                f"UPDATE {owner_sql}.{table_sql} SET "
                + ", ".join(set_parts)
                + f" WHERE {match_sql}",
                params,
            )
            await oracle_connection.commit()
            after_values = dict(before_values)
            after_values.update(safe_update_values)
            return {
                "action": "updated",
                "existing_rows": 1,
                "rowcount": rowcount,
                "generated_values": {},
                "before_values": before_values,
                "after_values": after_values,
            }

        except AppError:
            await oracle_connection.rollback()
            raise
        except oracledb.Error as exc:
            await oracle_connection.rollback()
            raise AppError(
                oracle_error_message(exc),
                code="PROVISIONING_TABLE_UPSERT_FAILED",
                status_code=400,
            ) from exc


async def get_oracle_user_deprovision_state(
    connection: dict,
    username: str,
) -> dict:
    """Return live account state and a conservative owned-object count."""
    username = normalize_oracle_identifier(username, field_name="Schema name")
    async with open_oracle_connection(connection) as oracle_connection:
        try:
            user_row = await oracle_connection.fetchone(
                """
                SELECT username, account_status
                FROM dba_users
                WHERE username = :username
                """,
                {"username": username},
            )
            if user_row is None:
                return {
                    "exists": False,
                    "account_status": None,
                    "owned_object_count": 0,
                }
            count_row = await oracle_connection.fetchone(
                "SELECT COUNT(*) FROM dba_objects WHERE owner = :username",
                {"username": username},
            )
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_DEPROVISION_LOOKUP_FAILED",
                status_code=400,
            ) from exc

    return {
        "exists": True,
        "account_status": user_row[1],
        "owned_object_count": int(count_row[0]) if count_row else 0,
    }


async def delete_oracle_provisioning_row(
    connection: dict,
    *,
    owner: str,
    table_name: str,
    match_values: dict[str, object],
) -> int:
    """Delete exactly one verified provisioning-table row and commit it."""
    owner = normalize_oracle_identifier(owner, field_name="Schema")
    table_name = normalize_oracle_identifier(table_name, field_name="Table")
    if not match_values:
        raise AppError(
            "At least one deprovision match column is required.",
            code="PROVISIONING_MATCH_REQUIRED",
            status_code=400,
        )

    owner_sql = quote_oracle_identifier(owner)
    table_sql = quote_oracle_identifier(table_name)
    match_sql, parameters = _build_match_clause(match_values)

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            count_row = await oracle_connection.fetchone(
                f"SELECT COUNT(*) FROM {owner_sql}.{table_sql} WHERE {match_sql}",
                parameters,
            )
            existing_rows = int(count_row[0]) if count_row else 0
            if existing_rows == 0:
                return 0
            if existing_rows != 1:
                raise AppError(
                    f"Deprovision match identifies {existing_rows} rows; exactly one row is required.",
                    code="PROVISIONING_DEPROVISION_AMBIGUOUS",
                    status_code=409,
                )
            rowcount = await oracle_connection.execute(
                f"DELETE FROM {owner_sql}.{table_sql} WHERE {match_sql}",
                parameters,
            )
            await oracle_connection.commit()
            return int(rowcount or 0)
        except AppError:
            raise
        except oracledb.Error as exc:
            try:
                await oracle_connection.rollback()
            except Exception:
                pass
            raise AppError(
                oracle_error_message(exc),
                code="PROVISIONING_DEPROVISION_DELETE_FAILED",
                status_code=400,
            ) from exc


async def drop_oracle_user(
    connection: dict,
    username: str,
    *,
    cascade: bool,
) -> None:
    """Drop one normalized Oracle user/schema after service-layer confirmation."""
    username = normalize_oracle_identifier(username, field_name="Schema name")
    sql = "DROP USER " + quote_oracle_identifier(username)
    if cascade:
        sql += " CASCADE"

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            await oracle_connection.execute(sql)
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_DEPROVISION_DROP_FAILED",
                status_code=400,
            ) from exc
