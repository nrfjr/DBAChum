from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.connectors.oracle_provisioning import (
    is_sensitive_reference_role,
    normalize_oracle_identifier,
)
from app.core.exceptions import AppError
from app.core.oracle_accounts import is_oracle_system_account


POWERFUL_ROLES = {
    "DBA",
    "RESOURCE",
    "SELECT_CATALOG_ROLE",
    "EXECUTE_CATALOG_ROLE",
    "DELETE_CATALOG_ROLE",
    "DATAPUMP_EXP_FULL_DATABASE",
    "DATAPUMP_IMP_FULL_DATABASE",
    "EXP_FULL_DATABASE",
    "IMP_FULL_DATABASE",
    "DV_ACCTMGR",
}

POWERFUL_SYSTEM_PRIVILEGES = {
    "ALTER DATABASE",
    "ALTER SYSTEM",
    "CREATE USER",
    "ALTER USER",
    "DROP USER",
    "BECOME USER",
    "GRANT ANY PRIVILEGE",
    "GRANT ANY ROLE",
    "GRANT ANY OBJECT PRIVILEGE",
    "SELECT ANY TABLE",
    "INSERT ANY TABLE",
    "UPDATE ANY TABLE",
    "DELETE ANY TABLE",
    "EXECUTE ANY PROCEDURE",
    "CREATE ANY PROCEDURE",
    "ALTER ANY PROCEDURE",
    "DROP ANY PROCEDURE",
    "CREATE ANY TABLE",
    "ALTER ANY TABLE",
    "DROP ANY TABLE",
    "CREATE ANY VIEW",
    "DROP ANY VIEW",
    "CREATE ANY TRIGGER",
    "ALTER ANY TRIGGER",
    "DROP ANY TRIGGER",
}

MAX_OBJECT_PRIVILEGES = 5000


def _ensure_inspectable_username(username: str) -> str:
    normalized = normalize_oracle_identifier(username, field_name="Username")
    if is_oracle_system_account(normalized):
        raise AppError(
            "Oracle-maintained/system accounts are hidden from the normal access inspector.",
            code="ORACLE_SYSTEM_ACCOUNT_PROTECTED",
            status_code=403,
        )
    return normalized


def _is_powerful_system_privilege(privilege: str) -> bool:
    normalized = privilege.upper()
    if normalized in POWERFUL_SYSTEM_PRIVILEGES:
        return True

    dangerous_prefixes = (
        "CREATE ANY ",
        "ALTER ANY ",
        "DROP ANY ",
        "SELECT ANY ",
        "INSERT ANY ",
        "UPDATE ANY ",
        "DELETE ANY ",
        "EXECUTE ANY ",
    )
    return normalized.startswith(dangerous_prefixes)


def _source_key(source: dict) -> tuple:
    return (
        source.get("kind"),
        tuple(source.get("via") or []),
        bool(source.get("admin_option")),
        source.get("default_role"),
        source.get("grantable"),
    )


def _append_source(target: list[dict], source: dict) -> None:
    key = _source_key(source)
    if all(_source_key(existing) != key for existing in target):
        target.append(source)


def _build_role_paths(
    direct_role_rows: list[tuple],
    role_grant_rows: list[tuple],
) -> dict[str, dict]:
    role_info: dict[str, dict] = {}
    queue: deque[str] = deque()

    for row in direct_role_rows:
        role = str(row[0]).upper()
        role_info[role] = {
            "path": [role],
            "direct": True,
            "admin_option": str(row[1]).upper() == "YES",
            "default_role": str(row[2]).upper() == "YES",
        }
        queue.append(role)

    children: dict[str, list[tuple[str, bool]]] = defaultdict(list)
    for row in role_grant_rows:
        grantee = str(row[0]).upper()
        granted_role = str(row[1]).upper()
        admin_option = str(row[2]).upper() == "YES"
        children[grantee].append((granted_role, admin_option))

    while queue:
        parent = queue.popleft()
        parent_path = role_info[parent]["path"]
        for child, admin_option in children.get(parent, []):
            if child in parent_path:
                continue
            candidate_path = [*parent_path, child]
            current = role_info.get(child)
            if current is None or len(candidate_path) < len(current["path"]):
                role_info[child] = {
                    "path": candidate_path,
                    "direct": False,

                    "admin_option": admin_option,
                    "default_role": None,
                }
                queue.append(child)

    return role_info


def _role_source(info: dict) -> dict:
    if info["direct"]:
        return {
            "kind": "direct",
            "via": [],
            "admin_option": bool(info.get("admin_option")),
            "default_role": info.get("default_role"),
            "grantable": None,
        }
    return {
        "kind": "role",
        "via": list(info.get("path") or []),
        "admin_option": False,
        "default_role": None,
        "grantable": None,
    }


def _privilege_source(
    grantee: str,
    username: str,
    role_info: dict[str, dict],
    *,
    admin_option: bool = False,
    grantable: bool | None = None,
) -> dict:
    normalized = grantee.upper()
    if normalized == username:
        return {
            "kind": "direct",
            "via": [],
            "admin_option": admin_option,
            "default_role": None,
            "grantable": grantable,
        }
    if normalized == "PUBLIC":
        return {
            "kind": "public",
            "via": ["PUBLIC"],
            "admin_option": False,
            "default_role": None,
            "grantable": grantable,
        }
    path = list(role_info.get(normalized, {}).get("path") or [normalized])
    return {
        "kind": "role",
        "via": path,
        "admin_option": False,
        "default_role": None,
        "grantable": grantable,
    }


def _aggregate_access(
    *,
    username: str,
    direct_role_rows: list[tuple],
    role_grant_rows: list[tuple],
    system_privilege_rows: list[tuple],
    object_privilege_rows: list[tuple],
    column_privilege_rows: list[tuple],
    administrative_privileges: list[str],
) -> dict:
    role_info = _build_role_paths(direct_role_rows, role_grant_rows)

    roles = []
    for role_name in sorted(role_info):
        info = role_info[role_name]
        roles.append(
            {
                "name": role_name,
                "sources": [_role_source(info)],
                "sensitive": is_sensitive_reference_role(role_name),
                "powerful": role_name in POWERFUL_ROLES or is_sensitive_reference_role(role_name),
            }
        )

    sys_map: dict[str, dict] = {}
    for row in system_privilege_rows:
        grantee = str(row[0]).upper()
        privilege = str(row[1]).upper()
        admin_option = str(row[2]).upper() == "YES"
        item = sys_map.setdefault(
            privilege,
            {
                "name": privilege,
                "sources": [],
                "powerful": _is_powerful_system_privilege(privilege),
            },
        )
        _append_source(
            item["sources"],
            _privilege_source(
                grantee,
                username,
                role_info,
                admin_option=admin_option,
            ),
        )
    system_privileges = [sys_map[key] for key in sorted(sys_map)]

    object_map: dict[tuple[str, str, str, str | None], dict] = {}

    def add_object_row(
        grantee: str,
        owner: str,
        object_name: str,
        privilege: str,
        grantable_value: str,
        column_name: str | None = None,
    ) -> None:
        key = (
            str(owner).upper(),
            str(object_name).upper(),
            str(privilege).upper(),
            str(column_name).upper() if column_name else None,
        )
        item = object_map.setdefault(
            key,
            {
                "owner": key[0],
                "object_name": key[1],
                "privilege": key[2],
                "column_name": key[3],
                "sources": [],
            },
        )
        _append_source(
            item["sources"],
            _privilege_source(
                str(grantee),
                username,
                role_info,
                grantable=str(grantable_value).upper() == "YES",
            ),
        )

    for row in object_privilege_rows:
        add_object_row(row[0], row[1], row[2], row[3], row[4])
    for row in column_privilege_rows:
        add_object_row(row[0], row[1], row[2], row[4], row[5], column_name=row[3])

    object_privileges = [
        object_map[key]
        for key in sorted(object_map, key=lambda value: (value[0], value[1], value[3] or "", value[2]))
    ]

    powerful_findings: list[dict] = []
    for item in roles:
        if item["powerful"]:
            source = item["sources"][0]
            source_text = "direct" if source["kind"] == "direct" else "via " + " → ".join(source["via"])
            powerful_findings.append(
                {
                    "kind": "role",
                    "name": item["name"],
                    "source": source_text,
                    "reason": "Elevated or sensitive Oracle role.",
                }
            )
    for item in system_privileges:
        if item["powerful"]:
            source = item["sources"][0]
            if source["kind"] == "direct":
                source_text = "direct"
            elif source["kind"] == "public":
                source_text = "PUBLIC"
            else:
                source_text = "via " + " → ".join(source["via"])
            powerful_findings.append(
                {
                    "kind": "system_privilege",
                    "name": item["name"],
                    "source": source_text,
                    "reason": "Broad system privilege with elevated database impact.",
                }
            )
    for privilege in sorted(set(administrative_privileges)):
        powerful_findings.append(
            {
                "kind": "administrative_privilege",
                "name": privilege,
                "source": "password file",
                "reason": "Oracle administrative privilege outside normal role grants.",
            }
        )

    return {
        "roles": roles,
        "system_privileges": system_privileges,
        "object_privileges": object_privileges,
        "administrative_privileges": sorted(set(administrative_privileges)),
        "powerful_findings": powerful_findings,
    }


async def _fetch_for_grantees(oracle_connection, sql_prefix: str, grantees: list[str]) -> list[tuple]:
    if not grantees:
        return []
    rows: list[tuple] = []
    for offset in range(0, len(grantees), 500):
        chunk = grantees[offset : offset + 500]
        binds = {f"g{i}": value for i, value in enumerate(chunk)}
        placeholders = ", ".join(f":g{i}" for i in range(len(chunk)))
        rows.extend(await oracle_connection.fetchall(sql_prefix.format(placeholders=placeholders), binds))
    return rows


async def _load_password_file_privileges(oracle_connection, username: str) -> tuple[list[str], str | None]:
    query_variants = [
        ("SYSDBA", "SYSOPER", "SYSASM", "SYSBACKUP", "SYSDG", "SYSKM"),
        ("SYSDBA", "SYSOPER", "SYSASM"),
        ("SYSDBA", "SYSOPER"),
    ]
    last_error: Exception | None = None
    for columns in query_variants:
        try:
            row = await oracle_connection.fetchone(
                "SELECT " + ", ".join(column.lower() for column in columns)
                + " FROM v$pwfile_users WHERE username = :username",
                {"username": username},
            )
            if row is None:
                return [], None
            privileges = [
                name for name, value in zip(columns, row) if str(value).upper() in {"TRUE", "YES", "Y"}
            ]
            return privileges, None
        except oracledb.Error as exc:
            last_error = exc
    return [], (
        "Password-file administrative privilege inspection is unavailable: "
        + oracle_error_message(last_error)
        if last_error is not None
        else None
    )


async def get_oracle_user_access_inspector(connection: dict, username: str) -> dict:
    username = _ensure_inspectable_username(username)
    warnings: list[str] = []

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            user_row = await oracle_connection.fetchone(
                """
                SELECT username, account_status, default_tablespace,
                       temporary_tablespace, profile, created, lock_date, expiry_date
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

            direct_role_rows = await oracle_connection.fetchall(
                """
                SELECT granted_role, admin_option, default_role
                FROM dba_role_privs
                WHERE grantee = :username
                ORDER BY granted_role
                """,
                {"username": username},
            )

            role_grant_rows = await oracle_connection.fetchall(
                """
                SELECT grantee, granted_role, admin_option, default_role
                FROM dba_role_privs
                WHERE grantee IN (SELECT role FROM dba_roles)
                ORDER BY grantee, granted_role
                """
            )
            role_info = _build_role_paths(direct_role_rows, role_grant_rows)
            effective_grantees = [username, *sorted(role_info), "PUBLIC"]

            try:
                system_privilege_rows = await _fetch_for_grantees(
                    oracle_connection,
                    """
                    SELECT grantee, privilege, admin_option
                    FROM dba_sys_privs
                    WHERE grantee IN ({placeholders})
                    ORDER BY grantee, privilege
                    """,
                    effective_grantees,
                )
            except oracledb.Error as exc:
                system_privilege_rows = []
                warnings.append(
                    "System privilege inspection is unavailable: " + oracle_error_message(exc)
                )

            try:
                object_privilege_rows = await _fetch_for_grantees(
                    oracle_connection,
                    """
                    SELECT grantee, owner, table_name, privilege, grantable
                    FROM dba_tab_privs
                    WHERE grantee IN ({placeholders})
                    ORDER BY owner, table_name, privilege, grantee
                    """,
                    effective_grantees,
                )
            except oracledb.Error as exc:
                object_privilege_rows = []
                warnings.append(
                    "Object privilege inspection is unavailable: " + oracle_error_message(exc)
                )

            try:
                column_privilege_rows = await _fetch_for_grantees(
                    oracle_connection,
                    """
                    SELECT grantee, owner, table_name, column_name, privilege, grantable
                    FROM dba_col_privs
                    WHERE grantee IN ({placeholders})
                    ORDER BY owner, table_name, column_name, privilege, grantee
                    """,
                    effective_grantees,
                )
            except oracledb.Error as exc:
                column_privilege_rows = []
                warnings.append(
                    "Column-level privilege inspection is unavailable: " + oracle_error_message(exc)
                )

            administrative_privileges, admin_warning = await _load_password_file_privileges(
                oracle_connection, username
            )
            if admin_warning:
                warnings.append(admin_warning)
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ACCESS_INSPECTOR_FAILED",
                status_code=400,
            ) from exc

    aggregated = _aggregate_access(
        username=username,
        direct_role_rows=direct_role_rows,
        role_grant_rows=role_grant_rows,
        system_privilege_rows=system_privilege_rows,
        object_privilege_rows=object_privilege_rows,
        column_privilege_rows=column_privilege_rows,
        administrative_privileges=administrative_privileges,
    )

    if len(aggregated["object_privileges"]) > MAX_OBJECT_PRIVILEGES:
        aggregated["object_privileges"] = aggregated["object_privileges"][:MAX_OBJECT_PRIVILEGES]
        warnings.append(
            f"Object privilege display was capped at {MAX_OBJECT_PRIVILEGES:,} entries for this user."
        )

    return {
        "username": str(user_row[0]),
        "status": str(user_row[1] or ""),
        "default_tablespace": user_row[2],
        "temporary_tablespace": user_row[3],
        "profile": user_row[4],
        "created_at": user_row[5],
        "lock_date": user_row[6],
        "expiry_date": user_row[7],
        **aggregated,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc),
    }
