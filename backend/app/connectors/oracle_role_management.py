from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.connectors.oracle_access_inspector import (
    POWERFUL_ROLES,
    _is_powerful_system_privilege,
)
from app.connectors.oracle_provisioning import (
    is_sensitive_reference_role,
    normalize_oracle_identifier,
    quote_oracle_identifier,
)
from app.core.exceptions import AppError
from app.core.oracle_accounts import is_oracle_system_account


PROTECTED_ORACLE_ROLES = {
    "DBA",
    "CONNECT",
    "RESOURCE",
    "SELECT_CATALOG_ROLE",
    "EXECUTE_CATALOG_ROLE",
    "DELETE_CATALOG_ROLE",
    "EXP_FULL_DATABASE",
    "IMP_FULL_DATABASE",
    "DATAPUMP_EXP_FULL_DATABASE",
    "DATAPUMP_IMP_FULL_DATABASE",
    "AQ_ADMINISTRATOR_ROLE",
    "AQ_USER_ROLE",
    "SCHEDULER_ADMIN",
    "HS_ADMIN_EXECUTE_ROLE",
    "HS_ADMIN_SELECT_ROLE",
    "HS_ADMIN_ROLE",
    "RECOVERY_CATALOG_OWNER",
    "OEM_ADVISOR",
    "OEM_MONITOR",
    "GATHER_SYSTEM_STATISTICS",
    "GLOBAL_AQ_USER_ROLE",
    "JAVAUSERPRIV",
    "JAVAIDPRIV",
    "JAVASYSPRIV",
    "JAVA_ADMIN",
    "WM_ADMIN_ROLE",
    "XDBADMIN",
    "XDB_SET_INVOKER",
    "AUTHENTICATEDUSER",
    "DV_ACCTMGR",
}

BLOCKED_ADMINISTRATIVE_PRIVILEGES = {
    "SYSDBA",
    "SYSOPER",
    "SYSASM",
    "SYSBACKUP",
    "SYSDG",
    "SYSKM",
    "SYSRAC",
}

OBJECT_PRIVILEGE_FALLBACK = {
    "ALTER",
    "DEBUG",
    "DELETE",
    "EXECUTE",
    "FLASHBACK",
    "INDEX",
    "INSERT",
    "READ",
    "REFERENCES",
    "SELECT",
    "UPDATE",
}

PRIVILEGE_PATTERN = re.compile(r"^[A-Z][A-Z0-9 _#$]{0,127}$")
MAX_ROLE_OBJECT_PRIVILEGES = 5000


def normalize_privilege(value: str, *, field_name: str = "Privilege") -> str:
    normalized = " ".join(value.strip().upper().split())
    if not normalized or not PRIVILEGE_PATTERN.fullmatch(normalized):
        raise AppError(
            f"{field_name} contains unsupported characters.",
            code="INVALID_ORACLE_PRIVILEGE",
            status_code=400,
        )
    return normalized


def _role_protection(name: str, oracle_maintained: bool = False) -> dict:
    normalized = name.upper()
    protected = (
        oracle_maintained
        or normalized in PROTECTED_ORACLE_ROLES
        or is_sensitive_reference_role(normalized)
    )
    powerful = normalized in POWERFUL_ROLES or is_sensitive_reference_role(normalized)
    return {
        "protected": protected,
        "powerful": powerful,
        "manageable": not protected,
    }


def is_protected_role_name(name: str) -> bool:
    normalized = normalize_oracle_identifier(name, field_name="Role")
    return _role_protection(normalized)["protected"]


def _ensure_manageable_role(role: dict) -> None:
    if not role.get("manageable"):
        raise AppError(
            f"Role {role['name']} is Oracle-maintained or protected and is inspect-only in DBAChum.",
            code="ORACLE_ROLE_PROTECTED",
            status_code=403,
        )


async def _load_role_rows(oracle_connection) -> tuple[list[tuple], bool]:
    try:
        rows = await oracle_connection.fetchall(
            "SELECT role, password_required, oracle_maintained FROM dba_roles ORDER BY role"
        )
        return rows, True
    except oracledb.Error:
        rows = await oracle_connection.fetchall(
            "SELECT role, password_required FROM dba_roles ORDER BY role"
        )
        return rows, False


def _role_from_row(row: tuple, oracle_maintained_available: bool) -> dict:
    name = str(row[0]).upper()
    maintained = (
        oracle_maintained_available
        and len(row) > 2
        and str(row[2]).upper() == "Y"
    )
    return {
        "name": name,
        "password_required": str(row[1]).upper() == "YES" if len(row) > 1 else False,
        "oracle_maintained": maintained,
        **_role_protection(name, maintained),
    }


async def _catalog_system_privileges(oracle_connection) -> tuple[list[str], str | None]:
    try:
        rows = await oracle_connection.fetchall(
            "SELECT name FROM system_privilege_map ORDER BY name"
        )
        return sorted({str(row[0]).upper() for row in rows}), None
    except oracledb.Error as primary:
        try:
            rows = await oracle_connection.fetchall(
                "SELECT DISTINCT privilege FROM dba_sys_privs ORDER BY privilege"
            )
            return sorted({str(row[0]).upper() for row in rows}), (
                "The complete Oracle system privilege catalog is unavailable; "
                "showing privileges currently present in DBA_SYS_PRIVS."
            )
        except oracledb.Error:
            return [], "System privilege catalog is unavailable: " + oracle_error_message(primary)


async def _catalog_object_privileges(oracle_connection) -> tuple[list[str], str | None]:
    try:
        rows = await oracle_connection.fetchall(
            "SELECT name FROM table_privilege_map ORDER BY name"
        )
        names = sorted({str(row[0]).upper() for row in rows})
        if names:
            return names, None
    except oracledb.Error:
        pass
    return sorted(OBJECT_PRIVILEGE_FALLBACK), None


async def get_oracle_roles(connection: dict) -> dict:
    warnings: list[str] = []
    async with open_oracle_connection(connection) as oracle_connection:
        try:
            role_rows, maintained_available = await _load_role_rows(oracle_connection)

            sys_catalog, sys_warning = await _catalog_system_privileges(oracle_connection)
            if sys_warning:
                warnings.append(sys_warning)
            object_catalog, object_warning = await _catalog_object_privileges(oracle_connection)
            if object_warning:
                warnings.append(object_warning)
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ROLE_LIST_FAILED",
                status_code=400,
            ) from exc

    roles = [
        _role_from_row(row, maintained_available)
        for row in role_rows
    ]

    return {
        "roles": roles,
        "system_privileges_catalog": sys_catalog,
        "object_privileges_catalog": object_catalog,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc),
    }



async def _get_role_metadata(oracle_connection, role_name: str) -> dict:
    role_name = normalize_oracle_identifier(role_name, field_name="Role")
    try:
        row = await oracle_connection.fetchone(
            "SELECT role, password_required, oracle_maintained FROM dba_roles WHERE role = :role",
            {"role": role_name},
        )
        maintained_available = True
    except oracledb.Error:
        row = await oracle_connection.fetchone(
            "SELECT role, password_required FROM dba_roles WHERE role = :role",
            {"role": role_name},
        )
        maintained_available = False
    if row is None:
        raise AppError(
            "Oracle role was not found.",
            code="ORACLE_ROLE_NOT_FOUND",
            status_code=404,
        )
    return _role_from_row(row, maintained_available)


async def get_oracle_role_detail(connection: dict, role_name: str) -> dict:
    role_name = normalize_oracle_identifier(role_name, field_name="Role")
    warnings: list[str] = []
    async with open_oracle_connection(connection) as oracle_connection:
        try:
            role = await _get_role_metadata(oracle_connection, role_name)
            members = await oracle_connection.fetchall(
                """
                SELECT p.grantee, u.account_status, p.admin_option, p.default_role
                FROM dba_role_privs p
                JOIN dba_users u ON u.username = p.grantee
                WHERE p.granted_role = :role
                ORDER BY p.grantee
                """,
                {"role": role_name},
            )
            parent_roles = await oracle_connection.fetchall(
                """
                SELECT p.grantee, p.admin_option
                FROM dba_role_privs p
                WHERE p.granted_role = :role
                  AND p.grantee IN (SELECT role FROM dba_roles)
                ORDER BY p.grantee
                """,
                {"role": role_name},
            )
            child_rows = await oracle_connection.fetchall(
                """
                SELECT granted_role, admin_option
                FROM dba_role_privs
                WHERE grantee = :role
                ORDER BY granted_role
                """,
                {"role": role_name},
            )
            system_rows = await oracle_connection.fetchall(
                """
                SELECT privilege, admin_option
                FROM dba_sys_privs
                WHERE grantee = :role
                ORDER BY privilege
                """,
                {"role": role_name},
            )
            try:
                object_rows = await oracle_connection.fetchall(
                    """
                    SELECT owner, table_name, privilege, grantable
                    FROM dba_tab_privs
                    WHERE grantee = :role
                    ORDER BY owner, table_name, privilege
                    """,
                    {"role": role_name},
                )
            except oracledb.Error as exc:
                object_rows = []
                warnings.append("Object privileges are unavailable: " + oracle_error_message(exc))
            try:
                column_rows = await oracle_connection.fetchall(
                    """
                    SELECT owner, table_name, column_name, privilege, grantable
                    FROM dba_col_privs
                    WHERE grantee = :role
                    ORDER BY owner, table_name, column_name, privilege
                    """,
                    {"role": role_name},
                )
            except oracledb.Error as exc:
                column_rows = []
                warnings.append("Column privileges are unavailable: " + oracle_error_message(exc))
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ROLE_DETAIL_FAILED",
                status_code=400,
            ) from exc

    child_roles = []
    for child_name, admin_option in child_rows:
        child_name = str(child_name).upper()
        child_roles.append(
            {
                "name": child_name,
                "admin_option": str(admin_option).upper() == "YES",
                **_role_protection(child_name),
            }
        )

    system_privileges = [
        {
            "name": str(privilege).upper(),
            "admin_option": str(admin_option).upper() == "YES",
            "powerful": _is_powerful_system_privilege(str(privilege)),
        }
        for privilege, admin_option in system_rows
    ]

    object_privileges = [
        {
            "owner": str(owner).upper(),
            "object_name": str(table_name).upper(),
            "privilege": str(privilege).upper(),
            "column_name": None,
            "grantable": str(grantable).upper() == "YES",
        }
        for owner, table_name, privilege, grantable in object_rows
    ]
    object_privileges.extend(
        {
            "owner": str(owner).upper(),
            "object_name": str(table_name).upper(),
            "privilege": str(privilege).upper(),
            "column_name": str(column_name).upper(),
            "grantable": str(grantable).upper() == "YES",
        }
        for owner, table_name, column_name, privilege, grantable in column_rows
    )
    object_privileges.sort(
        key=lambda item: (
            item["owner"],
            item["object_name"],
            item["column_name"] or "",
            item["privilege"],
        )
    )
    if len(object_privileges) > MAX_ROLE_OBJECT_PRIVILEGES:
        object_privileges = object_privileges[:MAX_ROLE_OBJECT_PRIVILEGES]
        warnings.append(
            f"Object privilege display was capped at {MAX_ROLE_OBJECT_PRIVILEGES:,} entries."
        )

    return {
        **role,
        "members": [
            {
                "username": str(username).upper(),
                "status": str(status or ""),
                "admin_option": str(admin_option).upper() == "YES",
                "default_role": str(default_role).upper() == "YES",
                "protected": is_oracle_system_account(str(username)),
            }
            for username, status, admin_option, default_role in members
        ],
        "parent_roles": [
            {
                "name": str(name).upper(),
                "admin_option": str(admin_option).upper() == "YES",
            }
            for name, admin_option in parent_roles
        ],
        "child_roles": child_roles,
        "system_privileges": system_privileges,
        "object_privileges": object_privileges,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc),
    }


async def oracle_role_exists(connection: dict, role_name: str) -> bool:
    role_name = normalize_oracle_identifier(role_name, field_name="Role")
    async with open_oracle_connection(connection) as oracle_connection:
        row = await oracle_connection.fetchone(
            "SELECT role FROM dba_roles WHERE role = :role", {"role": role_name}
        )
    return row is not None


async def create_oracle_role(connection: dict, role_name: str) -> None:
    role_name = normalize_oracle_identifier(role_name, field_name="Role")
    async with open_oracle_connection(connection) as oracle_connection:
        try:
            await oracle_connection.execute(
                f"CREATE ROLE {quote_oracle_identifier(role_name)}"
            )
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ROLE_CREATE_FAILED",
                status_code=400,
            ) from exc


def _graph_reaches(edges: dict[str, set[str]], start: str, target: str) -> bool:
    queue: deque[str] = deque([start])
    seen: set[str] = set()
    while queue:
        current = queue.popleft()
        if current == target:
            return True
        if current in seen:
            continue
        seen.add(current)
        queue.extend(edges.get(current, set()) - seen)
    return False


async def build_oracle_role_change_preview(
    connection: dict,
    role_name: str,
    *,
    operation: str,
    value: str | None = None,
    username: str | None = None,
    owner: str | None = None,
    object_name: str | None = None,
    privilege: str | None = None,
) -> dict:
    role_name = normalize_oracle_identifier(role_name, field_name="Role")
    warnings: list[str] = []

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            role = await _get_role_metadata(oracle_connection, role_name)
            _ensure_manageable_role(role)

            statement: str
            target: str
            powerful = False
            current = False

            if operation in {"grant_to_user", "revoke_from_user"}:
                resolved_user = normalize_oracle_identifier(username or value or "", field_name="Username")
                if is_oracle_system_account(resolved_user):
                    raise AppError(
                        "Oracle-maintained/system accounts cannot be changed through role management.",
                        code="ORACLE_SYSTEM_ACCOUNT_PROTECTED",
                        status_code=403,
                    )
                user_row = await oracle_connection.fetchone(
                    "SELECT username FROM dba_users WHERE username = :username",
                    {"username": resolved_user},
                )
                if user_row is None:
                    raise AppError("Oracle user/schema was not found.", code="ORACLE_USER_NOT_FOUND", status_code=404)
                existing = await oracle_connection.fetchone(
                    "SELECT granted_role FROM dba_role_privs WHERE grantee = :username AND granted_role = :role",
                    {"username": resolved_user, "role": role_name},
                )
                current = existing is not None
                target = resolved_user
                if operation == "grant_to_user":
                    statement = f"GRANT {quote_oracle_identifier(role_name)} TO {quote_oracle_identifier(resolved_user)}"
                else:
                    statement = f"REVOKE {quote_oracle_identifier(role_name)} FROM {quote_oracle_identifier(resolved_user)}"

            elif operation in {"grant_child_role", "revoke_child_role"}:
                child = normalize_oracle_identifier(value or "", field_name="Child role")
                if child == role_name:
                    raise AppError("A role cannot be granted to itself.", code="ORACLE_ROLE_SELF_GRANT", status_code=400)
                child_meta = await _get_role_metadata(oracle_connection, child)
                existing = await oracle_connection.fetchone(
                    "SELECT granted_role FROM dba_role_privs WHERE grantee = :role AND granted_role = :child",
                    {"role": role_name, "child": child},
                )
                current = existing is not None
                target = child
                powerful = bool(child_meta["powerful"] or child_meta["protected"])
                if operation == "grant_child_role":
                    if child_meta["protected"]:
                        raise AppError(
                            f"Protected role {child} cannot be newly nested into a custom role through DBAChum.",
                            code="ORACLE_PROTECTED_CHILD_ROLE_ADD_BLOCKED",
                            status_code=403,
                        )
                    hierarchy_rows = await oracle_connection.fetchall(
                        "SELECT grantee, granted_role FROM dba_role_privs WHERE grantee IN (SELECT role FROM dba_roles)"
                    )
                    edges: dict[str, set[str]] = defaultdict(set)
                    for grantee, granted in hierarchy_rows:
                        edges[str(grantee).upper()].add(str(granted).upper())
                    if _graph_reaches(edges, child, role_name):
                        raise AppError(
                            "This role grant would create a circular role hierarchy.",
                            code="ORACLE_ROLE_CYCLE_BLOCKED",
                            status_code=409,
                        )
                    statement = f"GRANT {quote_oracle_identifier(child)} TO {quote_oracle_identifier(role_name)}"
                else:
                    statement = f"REVOKE {quote_oracle_identifier(child)} FROM {quote_oracle_identifier(role_name)}"

            elif operation in {"grant_system_privilege", "revoke_system_privilege"}:
                system_privilege = normalize_privilege(privilege or value or "", field_name="System privilege")
                if system_privilege in BLOCKED_ADMINISTRATIVE_PRIVILEGES:
                    raise AppError(
                        f"{system_privilege} is an Oracle administrative privilege and remains manual/inspect-only.",
                        code="ORACLE_ADMIN_PRIVILEGE_BLOCKED",
                        status_code=403,
                    )
                catalog, catalog_warning = await _catalog_system_privileges(oracle_connection)
                if catalog_warning:
                    warnings.append(catalog_warning)
                if system_privilege not in set(catalog):
                    raise AppError(
                        f"System privilege {system_privilege} could not be validated against this database.",
                        code="ORACLE_SYSTEM_PRIVILEGE_UNKNOWN",
                        status_code=400,
                    )
                existing = await oracle_connection.fetchone(
                    "SELECT privilege FROM dba_sys_privs WHERE grantee = :role AND privilege = :privilege",
                    {"role": role_name, "privilege": system_privilege},
                )
                current = existing is not None
                target = system_privilege
                powerful = _is_powerful_system_privilege(system_privilege)
                if powerful:
                    warnings.append(
                        f"{system_privilege} is broad/elevated access. Review the exact statement before execution."
                    )
                verb = "GRANT" if operation == "grant_system_privilege" else "REVOKE"
                prep = "TO" if operation == "grant_system_privilege" else "FROM"
                statement = f"{verb} {system_privilege} {prep} {quote_oracle_identifier(role_name)}"

            elif operation in {"grant_object_privilege", "revoke_object_privilege"}:
                resolved_owner = normalize_oracle_identifier(owner or "", field_name="Object owner")
                resolved_object = normalize_oracle_identifier(object_name or "", field_name="Object name")
                object_privilege = normalize_privilege(privilege or value or "", field_name="Object privilege")
                object_catalog, _ = await _catalog_object_privileges(oracle_connection)
                if object_privilege not in set(object_catalog):
                    raise AppError(
                        f"Object privilege {object_privilege} could not be validated against this database.",
                        code="ORACLE_OBJECT_PRIVILEGE_UNKNOWN",
                        status_code=400,
                    )
                object_row = await oracle_connection.fetchone(
                    "SELECT object_type FROM dba_objects WHERE owner = :owner AND object_name = :object_name AND ROWNUM = 1",
                    {"owner": resolved_owner, "object_name": resolved_object},
                )
                if object_row is None:
                    raise AppError(
                        "Oracle object was not found.",
                        code="ORACLE_OBJECT_NOT_FOUND",
                        status_code=404,
                    )
                existing = await oracle_connection.fetchone(
                    """
                    SELECT privilege FROM dba_tab_privs
                    WHERE grantee = :role AND owner = :owner
                      AND table_name = :object_name AND privilege = :privilege
                    """,
                    {
                        "role": role_name,
                        "owner": resolved_owner,
                        "object_name": resolved_object,
                        "privilege": object_privilege,
                    },
                )
                current = existing is not None
                target = f"{object_privilege} ON {resolved_owner}.{resolved_object}"
                verb = "GRANT" if operation == "grant_object_privilege" else "REVOKE"
                prep = "TO" if operation == "grant_object_privilege" else "FROM"
                statement = (
                    f"{verb} {object_privilege} ON "
                    f"{quote_oracle_identifier(resolved_owner)}.{quote_oracle_identifier(resolved_object)} "
                    f"{prep} {quote_oracle_identifier(role_name)}"
                )
            else:
                raise AppError(
                    "Unsupported Oracle role action.",
                    code="ORACLE_ROLE_ACTION_INVALID",
                    status_code=400,
                )
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ROLE_PREVIEW_FAILED",
                status_code=400,
            ) from exc

    is_grant = operation.startswith("grant_")
    ready = (is_grant and not current) or ((not is_grant) and current)
    if not ready:
        warnings.append(
            "No change is required because this grant is already present."
            if is_grant
            else "No change is required because this grant is not currently present."
        )

    return {
        "operation": operation,
        "role_name": role_name,
        "target": target,
        "statement": statement,
        "ready_to_execute": ready,
        "powerful": powerful,
        "warnings": warnings,
        "generated_at": datetime.now(timezone.utc),
    }


async def execute_oracle_role_statement(connection: dict, statement: str) -> None:
    async with open_oracle_connection(connection) as oracle_connection:
        try:
            await oracle_connection.execute(statement)
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ROLE_ACTION_FAILED",
                status_code=400,
            ) from exc


async def drop_oracle_role(connection: dict, role_name: str) -> None:
    role_name = normalize_oracle_identifier(role_name, field_name="Role")
    async with open_oracle_connection(connection) as oracle_connection:
        try:
            role = await _get_role_metadata(oracle_connection, role_name)
            _ensure_manageable_role(role)
            await oracle_connection.execute(
                f"DROP ROLE {quote_oracle_identifier(role_name)}"
            )
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ROLE_DROP_FAILED",
                status_code=400,
            ) from exc
