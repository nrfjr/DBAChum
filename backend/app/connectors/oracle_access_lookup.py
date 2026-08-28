from __future__ import annotations

import re
from collections import defaultdict, deque
from datetime import datetime, timezone

import oracledb

from app.connectors.oracle import open_oracle_connection, oracle_error_message
from app.connectors.oracle_access_inspector import POWERFUL_ROLES, _is_powerful_system_privilege
from app.connectors.oracle_provisioning import is_sensitive_reference_role, normalize_oracle_identifier
from app.core.exceptions import AppError
from app.core.oracle_accounts import is_oracle_system_account

MAX_LOOKUP_ROWS = 10000
_PRIVILEGE_RE = re.compile(r"^[A-Z0-9_$# ]+$")


EXPLICIT_PRIVILEGE_TO_ANY = {
    "SELECT": {"SELECT ANY TABLE", "SELECT ANY SEQUENCE"},
    "INSERT": {"INSERT ANY TABLE"},
    "UPDATE": {"UPDATE ANY TABLE"},
    "DELETE": {"DELETE ANY TABLE"},
    "LOCK": {"LOCK ANY TABLE"},
    "EXECUTE": {"EXECUTE ANY PROCEDURE", "EXECUTE ANY TYPE"},
    "DEBUG": {"DEBUG ANY PROCEDURE"},
    "ALTER": {"ALTER ANY SEQUENCE"},
    "UNDER": {"UNDER ANY TYPE"},
}


OBJECT_ANY_PRIVILEGES: dict[str, tuple[str, ...]] = {
    "TABLE": (
        "SELECT ANY TABLE",
        "INSERT ANY TABLE",
        "UPDATE ANY TABLE",
        "DELETE ANY TABLE",
        "LOCK ANY TABLE",
    ),
    "VIEW": (
        "SELECT ANY TABLE",
        "INSERT ANY TABLE",
        "UPDATE ANY TABLE",
        "DELETE ANY TABLE",
    ),
    "MATERIALIZED VIEW": (
        "SELECT ANY TABLE",
        "INSERT ANY TABLE",
        "UPDATE ANY TABLE",
        "DELETE ANY TABLE",
    ),
    "SEQUENCE": (
        "SELECT ANY SEQUENCE",
        "ALTER ANY SEQUENCE",
    ),
    "PROCEDURE": (
        "EXECUTE ANY PROCEDURE",
        "DEBUG ANY PROCEDURE",
    ),
    "FUNCTION": (
        "EXECUTE ANY PROCEDURE",
        "DEBUG ANY PROCEDURE",
    ),
    "PACKAGE": (
        "EXECUTE ANY PROCEDURE",
        "DEBUG ANY PROCEDURE",
    ),
    "TYPE": (
        "EXECUTE ANY TYPE",
        "UNDER ANY TYPE",
    ),
}


def _normalize_lookup_privilege(value: str | None, *, required: bool = True) -> str | None:
    normalized = (value or "").strip().upper()
    if not normalized:
        if required:
            raise AppError(
                "Privilege is required.",
                code="ORACLE_ACCESS_LOOKUP_PRIVILEGE_REQUIRED",
                status_code=422,
            )
        return None
    if len(normalized) > 128 or not _PRIVILEGE_RE.fullmatch(normalized):
        raise AppError(
            "Privilege contains unsupported characters.",
            code="ORACLE_ACCESS_LOOKUP_PRIVILEGE_INVALID",
            status_code=422,
        )
    return normalized


def _normal_user_map(rows: list[tuple], has_oracle_maintained: bool) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in rows:
        username = str(row[0]).upper()
        if is_oracle_system_account(username):
            continue
        if has_oracle_maintained and len(row) > 2 and str(row[2]).upper() == "Y":
            continue
        result[username] = str(row[1] or "")
    return result


async def _load_users(oracle_connection) -> dict[str, str]:
    try:
        rows = await oracle_connection.fetchall(
            """
            SELECT username, account_status, oracle_maintained
            FROM dba_users
            ORDER BY username
            """
        )
        return _normal_user_map(rows, True)
    except oracledb.Error:
        rows = await oracle_connection.fetchall(
            """
            SELECT username, account_status
            FROM dba_users
            ORDER BY username
            """
        )
        return _normal_user_map(rows, False)


def _build_role_paths_for_users(
    users: dict[str, str],
    role_grant_rows: list[tuple],
    role_names: set[str],
) -> dict[str, dict[str, dict]]:
    direct_by_user: dict[str, list[tuple[str, bool, bool]]] = defaultdict(list)
    children: dict[str, list[tuple[str, bool]]] = defaultdict(list)

    for row in role_grant_rows:
        grantee = str(row[0]).upper()
        role = str(row[1]).upper()
        admin_option = str(row[2]).upper() == "YES"
        default_role = str(row[3]).upper() == "YES"
        if grantee in users:
            direct_by_user[grantee].append((role, admin_option, default_role))
        elif grantee in role_names:
            children[grantee].append((role, admin_option))

    result: dict[str, dict[str, dict]] = {}
    for username in users:
        paths: dict[str, dict] = {}
        queue: deque[str] = deque()
        for role, admin_option, default_role in direct_by_user.get(username, []):
            current = paths.get(role)
            candidate = {
                "path": [role],
                "direct": True,
                "admin_option": admin_option,
                "default_role": default_role,
            }
            if current is None or len(candidate["path"]) < len(current["path"]):
                paths[role] = candidate
                queue.append(role)

        while queue:
            parent = queue.popleft()
            parent_path = paths[parent]["path"]
            for child, _role_admin_option in children.get(parent, []):
                if child in parent_path:
                    continue
                candidate_path = [*parent_path, child]
                current = paths.get(child)
                if current is None or len(candidate_path) < len(current["path"]):
                    paths[child] = {
                        "path": candidate_path,
                        "direct": False,
                        "admin_option": False,
                        "default_role": None,
                    }
                    queue.append(child)
        result[username] = paths

    return result


def _source_from_role_path(info: dict) -> dict:
    if info.get("direct"):
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


def _source_for_grantee(
    grantee: str,
    username: str,
    user_role_paths: dict[str, dict[str, dict]],
    *,
    admin_option: bool = False,
    grantable: bool | None = None,
) -> dict | None:
    normalized = grantee.upper()
    if normalized == username:
        return {
            "kind": "direct",
            "via": [],
            "admin_option": admin_option,
            "default_role": None,
            "grantable": grantable,
        }
    info = user_role_paths.get(username, {}).get(normalized)
    if info is None:
        return None
    return {
        "kind": "role",
        "via": list(info.get("path") or [normalized]),
        "admin_option": False,
        "default_role": None,
        "grantable": grantable,
    }


def _append_match(matches: list[dict], item: dict, seen: set[tuple]) -> None:
    source = item["source"]
    key = (
        item["username"],
        item.get("basis"),
        item.get("privilege"),
        item.get("column_name"),
        source.get("kind"),
        tuple(source.get("via") or []),
    )
    if key in seen:
        return
    seen.add(key)
    matches.append(item)


def _role_matches(
    users: dict[str, str],
    user_role_paths: dict[str, dict[str, dict]],
    role: str,
) -> list[dict]:
    matches: list[dict] = []
    for username in sorted(users):
        info = user_role_paths.get(username, {}).get(role)
        if info is None:
            continue
        matches.append(
            {
                "username": username,
                "status": users[username],
                "basis": "ROLE",
                "privilege": role,
                "column_name": None,
                "source": _source_from_role_path(info),
                "powerful": role in POWERFUL_ROLES or is_sensitive_reference_role(role),
            }
        )
    return matches


def _privilege_matches(
    *,
    users: dict[str, str],
    user_role_paths: dict[str, dict[str, dict]],
    rows: list[tuple],
    basis: str,
    privilege_override: str | None = None,
    powerful_override: bool | None = None,
) -> tuple[list[dict], list[str]]:
    matches: list[dict] = []
    public_details: list[str] = []
    seen: set[tuple] = set()

    for row in rows:
        grantee = str(row[0]).upper()
        privilege = privilege_override or str(row[1]).upper()
        admin_option = len(row) > 2 and str(row[2]).upper() == "YES"
        if grantee == "PUBLIC":
            if privilege not in public_details:
                public_details.append(privilege)
            continue

        for username in users:
            source = _source_for_grantee(
                grantee,
                username,
                user_role_paths,
                admin_option=admin_option,
            )
            if source is None:
                continue
            _append_match(
                matches,
                {
                    "username": username,
                    "status": users[username],
                    "basis": basis,
                    "privilege": privilege,
                    "column_name": None,
                    "source": source,
                    "powerful": (
                        powerful_override
                        if powerful_override is not None
                        else _is_powerful_system_privilege(privilege)
                    ),
                },
                seen,
            )

    matches.sort(key=lambda item: (item["username"], item.get("privilege") or ""))
    return matches, sorted(public_details)


def _object_matches(
    *,
    users: dict[str, str],
    user_role_paths: dict[str, dict[str, dict]],
    table_rows: list[tuple],
    column_rows: list[tuple],
    system_rows: list[tuple],
) -> tuple[list[dict], list[str]]:
    matches: list[dict] = []
    public_details: list[str] = []
    seen: set[tuple] = set()

    def add_explicit(row: tuple, *, column: bool) -> None:
        grantee = str(row[0]).upper()
        privilege = str(row[1]).upper()
        column_name = str(row[2]).upper() if column and row[2] else None
        grantable_index = 3 if column else 2
        grantable = str(row[grantable_index]).upper() == "YES"
        if grantee == "PUBLIC":
            detail = f"{privilege} ({'column ' + column_name if column_name else 'object'})"
            if detail not in public_details:
                public_details.append(detail)
            return
        for username in users:
            source = _source_for_grantee(
                grantee,
                username,
                user_role_paths,
                grantable=grantable,
            )
            if source is None:
                continue
            _append_match(
                matches,
                {
                    "username": username,
                    "status": users[username],
                    "basis": "COLUMN PRIVILEGE" if column else "OBJECT PRIVILEGE",
                    "privilege": privilege,
                    "column_name": column_name,
                    "source": source,
                    "powerful": False,
                },
                seen,
            )

    for row in table_rows:
        add_explicit(row, column=False)
    for row in column_rows:
        add_explicit(row, column=True)

    system_matches, system_public = _privilege_matches(
        users=users,
        user_role_paths=user_role_paths,
        rows=system_rows,
        basis="SYSTEM PRIVILEGE",
    )
    for item in system_matches:
        _append_match(matches, item, seen)
    for detail in system_public:
        if detail not in public_details:
            public_details.append(detail)

    matches.sort(
        key=lambda item: (
            item["username"],
            item["basis"],
            item.get("privilege") or "",
            item.get("column_name") or "",
        )
    )
    return matches, sorted(public_details)


async def _load_role_context(oracle_connection, users: dict[str, str]):
    role_rows = await oracle_connection.fetchall("SELECT role FROM dba_roles ORDER BY role")
    role_names = {str(row[0]).upper() for row in role_rows}
    role_grant_rows = await oracle_connection.fetchall(
        """
        SELECT grantee, granted_role, admin_option, default_role
        FROM dba_role_privs
        ORDER BY grantee, granted_role
        """
    )
    return role_names, _build_role_paths_for_users(users, role_grant_rows, role_names)


def _cap_matches(matches: list[dict], warnings: list[str]) -> list[dict]:
    if len(matches) <= MAX_LOOKUP_ROWS:
        return matches
    warnings.append(
        f"Access lookup was capped at {MAX_LOOKUP_ROWS:,} result rows. Narrow the search if needed."
    )
    return matches[:MAX_LOOKUP_ROWS]


async def get_oracle_access_lookup(
    connection: dict,
    *,
    kind: str,
    value: str | None = None,
    owner: str | None = None,
    object_name: str | None = None,
    privilege: str | None = None,
) -> dict:
    lookup_kind = (kind or "").strip().lower()
    if lookup_kind not in {"role", "system_privilege", "object"}:
        raise AppError(
            "Lookup type must be role, system_privilege, or object.",
            code="ORACLE_ACCESS_LOOKUP_KIND_INVALID",
            status_code=422,
        )

    warnings: list[str] = []
    public_details: list[str] = []
    target_exists = True
    object_type: str | None = None
    powerful = False

    async with open_oracle_connection(connection) as oracle_connection:
        try:
            users = await _load_users(oracle_connection)
            role_names, user_role_paths = await _load_role_context(oracle_connection, users)

            if lookup_kind == "role":
                target = normalize_oracle_identifier(value or "", field_name="Role")
                target_exists = target in role_names
                matches = _role_matches(users, user_role_paths, target) if target_exists else []
                powerful = target in POWERFUL_ROLES or is_sensitive_reference_role(target)

            elif lookup_kind == "system_privilege":
                target = _normalize_lookup_privilege(value)
                rows = await oracle_connection.fetchall(
                    """
                    SELECT grantee, privilege, admin_option
                    FROM dba_sys_privs
                    WHERE privilege = :privilege
                    ORDER BY grantee
                    """,
                    {"privilege": target},
                )
                matches, public_details = _privilege_matches(
                    users=users,
                    user_role_paths=user_role_paths,
                    rows=rows,
                    basis="SYSTEM PRIVILEGE",
                    privilege_override=target,
                )
                target_exists = bool(rows)
                powerful = _is_powerful_system_privilege(target)

            else:
                owner_name = normalize_oracle_identifier(owner or "", field_name="Owner")
                object_name_normalized = normalize_oracle_identifier(
                    object_name or "", field_name="Object name"
                )
                privilege_filter = _normalize_lookup_privilege(privilege, required=False)
                target = f"{owner_name}.{object_name_normalized}"

                object_row = await oracle_connection.fetchone(
                    """
                    SELECT object_type
                    FROM dba_objects
                    WHERE owner = :owner
                      AND object_name = :object_name
                      AND ROWNUM = 1
                    """,
                    {"owner": owner_name, "object_name": object_name_normalized},
                )
                if object_row is None:
                    target_exists = False
                    matches = []
                else:
                    object_type = str(object_row[0]).upper()
                    table_sql = """
                        SELECT grantee, privilege, grantable
                        FROM dba_tab_privs
                        WHERE owner = :owner
                          AND table_name = :object_name
                    """
                    column_sql = """
                        SELECT grantee, privilege, column_name, grantable
                        FROM dba_col_privs
                        WHERE owner = :owner
                          AND table_name = :object_name
                    """
                    params = {"owner": owner_name, "object_name": object_name_normalized}
                    if privilege_filter:
                        table_sql += " AND privilege = :privilege"
                        column_sql += " AND privilege = :privilege"
                        params["privilege"] = privilege_filter
                    table_sql += " ORDER BY grantee, privilege"
                    column_sql += " ORDER BY grantee, privilege, column_name"
                    table_rows = await oracle_connection.fetchall(table_sql, params)
                    column_rows = await oracle_connection.fetchall(column_sql, params)

                    any_privileges = list(OBJECT_ANY_PRIVILEGES.get(object_type, ()))
                    if privilege_filter:
                        allowed_any = EXPLICIT_PRIVILEGE_TO_ANY.get(privilege_filter, set())
                        any_privileges = [
                            item for item in any_privileges if item in allowed_any
                        ]
                    system_rows: list[tuple] = []
                    if any_privileges:
                        binds = {f"p{i}": item for i, item in enumerate(any_privileges)}
                        placeholders = ", ".join(f":p{i}" for i in range(len(any_privileges)))
                        system_rows = await oracle_connection.fetchall(
                            f"""
                            SELECT grantee, privilege, admin_option
                            FROM dba_sys_privs
                            WHERE privilege IN ({placeholders})
                            ORDER BY privilege, grantee
                            """,
                            binds,
                        )
                    elif object_type:
                        warnings.append(
                            f"Broad ANY-style privilege expansion is not defined for Oracle object type {object_type}. Explicit object/column grants are still shown."
                        )

                    matches, public_details = _object_matches(
                        users=users,
                        user_role_paths=user_role_paths,
                        table_rows=table_rows,
                        column_rows=column_rows,
                        system_rows=system_rows,
                    )

                    if privilege_filter:
                        matches = [
                            item for item in matches
                            if item["basis"] == "SYSTEM PRIVILEGE"
                            or item.get("privilege") == privilege_filter
                        ]

            matches = _cap_matches(matches, warnings)
            unique_user_count = len({item["username"] for item in matches})
        except AppError:
            raise
        except oracledb.Error as exc:
            raise AppError(
                oracle_error_message(exc),
                code="ORACLE_ACCESS_LOOKUP_FAILED",
                status_code=400,
            ) from exc

    return {
        "lookup_type": lookup_kind,
        "target": target,
        "target_exists": target_exists,
        "object_type": object_type,
        "matches": matches,
        "unique_user_count": unique_user_count,
        "public_access": bool(public_details),
        "public_details": public_details,
        "powerful": powerful,
        "warnings": warnings,
        "checked_at": datetime.now(timezone.utc),
    }
