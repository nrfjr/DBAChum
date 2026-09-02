from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from app.connectors.sqlserver_compat import (
    open_sqlserver_connection,
    probe_sqlserver_identity,
    sqlserver_error_message,
)
from app.core.exceptions import AppError


MAX_PERMISSION_ROWS = 1000

FIXED_SERVER_ROLES = (
    ("sysadmin", "critical"),
    ("securityadmin", "high"),
    ("serveradmin", "high"),
    ("setupadmin", "medium"),
    ("processadmin", "medium"),
    ("diskadmin", "medium"),
    ("dbcreator", "high"),
    ("bulkadmin", "medium"),
)

ELEVATED_DATABASE_ROLES = {
    "db_owner": "critical",
    "db_securityadmin": "high",
    "db_accessadmin": "medium",
    "db_ddladmin": "high",
    "db_backupoperator": "medium",
}

ELEVATED_SERVER_PERMISSIONS = {
    "CONTROL SERVER": "critical",
    "ALTER ANY LOGIN": "high",
    "IMPERSONATE ANY LOGIN": "high",
    "ALTER ANY SERVER ROLE": "high",
    "CREATE ANY DATABASE": "high",
    "ALTER SERVER STATE": "high",
    "VIEW SERVER STATE": "medium",
}

ELEVATED_DATABASE_PERMISSIONS = {
    "CONTROL": "high",
    "IMPERSONATE": "high",
    "ALTER ANY USER": "high",
    "ALTER ANY ROLE": "high",
    "CREATE USER": "medium",
    "CREATE ROLE": "medium",
    "ALTER": "medium",
}

LEGACY_PERMISSION_ACTIONS = {
    26: "REFERENCES",
    193: "SELECT",
    195: "INSERT",
    196: "DELETE",
    197: "UPDATE",
    224: "EXECUTE",
}

LEGACY_PROTECT_TYPES = {
    204: "GRANT_WITH_GRANT_OPTION",
    205: "GRANT",
    206: "DENY",
}


def _rows(cursor, sql: str) -> list[Any]:
    cursor.execute(sql)
    return list(cursor.fetchall())


def _safe_rows(cursor, sql: str, warning: str, warnings: list[str]) -> list[Any]:
    try:
        return _rows(cursor, sql)
    except Exception:
        warnings.append(warning)
        return []


def _server_role_memberships_from_syslogins(cursor, warnings: list[str]) -> list[dict]:
    rows = _safe_rows(
        cursor,
        """
        SELECT
            name,
            sysadmin,
            securityadmin,
            serveradmin,
            setupadmin,
            processadmin,
            diskadmin,
            dbcreator,
            bulkadmin
        FROM master.dbo.syslogins
        WHERE name NOT LIKE '##%'
        ORDER BY name
        """,
        "Fixed server-role membership could not be read. The connected login may not be allowed to enumerate all server principals.",
        warnings,
    )

    items: list[dict] = []
    role_names = [name for name, _severity in FIXED_SERVER_ROLES]
    for row in rows:
        for index, role_name in enumerate(role_names, start=1):
            try:
                enabled = bool(row[index])
            except Exception:
                enabled = False
            if enabled:
                items.append({
                    "principal": row[0],
                    "role": role_name,
                    "source": "fixed_server_role",
                })
    return items


def _modern_custom_server_roles(cursor, warnings: list[str]) -> list[dict]:
    rows = _safe_rows(
        cursor,
        """
        SELECT
            member.name,
            role.name
        FROM sys.server_role_members membership
        INNER JOIN sys.server_principals member
            ON member.principal_id = membership.member_principal_id
        INNER JOIN sys.server_principals role
            ON role.principal_id = membership.role_principal_id
        WHERE role.name NOT IN (
            'sysadmin', 'securityadmin', 'serveradmin', 'setupadmin',
            'processadmin', 'diskadmin', 'dbcreator', 'bulkadmin'
        )
        ORDER BY member.name, role.name
        """,
        "Custom server-role membership could not be read.",
        warnings,
    )
    return [
        {"principal": row[0], "role": row[1], "source": "server_role"}
        for row in rows
    ]


def _database_role_memberships(
    cursor,
    modern: bool,
    warnings: list[str],
) -> list[dict]:
    if modern:
        sql = """
            SELECT
                member.name,
                role.name
            FROM sys.database_role_members membership
            INNER JOIN sys.database_principals member
                ON member.principal_id = membership.member_principal_id
            INNER JOIN sys.database_principals role
                ON role.principal_id = membership.role_principal_id
            ORDER BY member.name, role.name
        """
    else:
        sql = """
            SELECT
                member.name,
                role.name
            FROM dbo.sysmembers membership
            INNER JOIN dbo.sysusers member
                ON member.uid = membership.memberuid
            INNER JOIN dbo.sysusers role
                ON role.uid = membership.groupuid
            ORDER BY member.name, role.name
        """

    rows = _safe_rows(
        cursor,
        sql,
        "Database-role membership could not be read for this database.",
        warnings,
    )
    return [
        {"principal": row[0], "role": row[1], "source": "database_role"}
        for row in rows
    ]


def _modern_logins(cursor, warnings: list[str]) -> list[dict]:
    rows = _safe_rows(
        cursor,
        """
        SELECT
            name,
            type_desc,
            is_disabled,
            default_database_name,
            create_date,
            modify_date
        FROM sys.server_principals
        WHERE type IN ('S', 'U', 'G', 'E', 'X')
          AND name NOT LIKE '##%'
        ORDER BY name
        """,
        "Server login details could not be read. The connected login may only be able to see a subset of principals.",
        warnings,
    )
    return [
        {
            "name": row[0],
            "principal_type": row[1] or "UNKNOWN",
            "disabled": bool(row[2]),
            "default_database": row[3],
            "created_at": row[4],
            "modified_at": row[5],
        }
        for row in rows
    ]


def _legacy_logins(cursor, warnings: list[str]) -> list[dict]:
    rows = _safe_rows(
        cursor,
        """
        SELECT
            name,
            CASE
                WHEN isntgroup = 1 THEN 'WINDOWS_GROUP'
                WHEN isntuser = 1 THEN 'WINDOWS_LOGIN'
                WHEN isntname = 1 THEN 'WINDOWS_PRINCIPAL'
                ELSE 'SQL_LOGIN'
            END,
            CASE WHEN denylogin = 1 OR hasaccess = 0 THEN 1 ELSE 0 END,
            dbname,
            createdate,
            updatedate
        FROM master.dbo.syslogins
        WHERE name NOT LIKE '##%'
        ORDER BY name
        """,
        "Legacy server login details could not be read.",
        warnings,
    )
    return [
        {
            "name": row[0],
            "principal_type": row[1] or "UNKNOWN",
            "disabled": bool(row[2]),
            "default_database": row[3],
            "created_at": row[4],
            "modified_at": row[5],
        }
        for row in rows
    ]


def _modern_database_users(cursor, major: int | None, warnings: list[str]) -> list[dict]:
    if major is not None and major >= 11:
        sql = """
            SELECT
                dp.name,
                dp.type_desc,
                SUSER_SNAME(dp.sid),
                dp.default_schema_name,
                dp.create_date,
                dp.modify_date,
                dp.authentication_type_desc,
                CASE
                    WHEN dp.authentication_type_desc = 'DATABASE' THEN 0
                    WHEN dp.type = 'S' AND dp.sid IS NOT NULL AND SUSER_SNAME(dp.sid) IS NULL THEN 1
                    ELSE 0
                END
            FROM sys.database_principals dp
            WHERE dp.principal_id > 4
              AND dp.type IN ('S', 'U', 'G', 'E', 'X')
            ORDER BY dp.name
        """
    else:
        sql = """
            SELECT
                dp.name,
                dp.type_desc,
                SUSER_SNAME(dp.sid),
                dp.default_schema_name,
                dp.create_date,
                dp.modify_date,
                NULL,
                CASE
                    WHEN dp.type = 'S' AND dp.sid IS NOT NULL AND SUSER_SNAME(dp.sid) IS NULL THEN 1
                    ELSE 0
                END
            FROM sys.database_principals dp
            WHERE dp.principal_id > 4
              AND dp.type IN ('S', 'U', 'G', 'E', 'X')
            ORDER BY dp.name
        """

    rows = _safe_rows(
        cursor,
        sql,
        "Database principal details could not be read.",
        warnings,
    )
    return [
        {
            "name": row[0],
            "principal_type": row[1] or "UNKNOWN",
            "login_name": row[2],
            "default_schema": row[3],
            "created_at": row[4],
            "modified_at": row[5],
            "authentication_type": row[6],
            "orphaned": bool(row[7]),
        }
        for row in rows
    ]


def _legacy_database_users(cursor, warnings: list[str]) -> list[dict]:
    rows = _safe_rows(
        cursor,
        """
        SELECT
            u.name,
            CASE
                WHEN u.isntgroup = 1 THEN 'WINDOWS_GROUP'
                WHEN u.isntuser = 1 THEN 'WINDOWS_USER'
                WHEN u.issqluser = 1 THEN 'SQL_USER'
                ELSE 'DATABASE_PRINCIPAL'
            END,
            l.name,
            NULL,
            u.createdate,
            u.updatedate,
            NULL,
            CASE
                WHEN u.issqluser = 1 AND l.name IS NULL THEN 1
                ELSE 0
            END
        FROM dbo.sysusers u
        LEFT JOIN master.dbo.syslogins l
            ON l.sid = u.sid
        WHERE u.uid > 4
          AND (u.issqluser = 1 OR u.isntuser = 1 OR u.isntgroup = 1)
        ORDER BY u.name
        """,
        "Legacy database user details could not be read.",
        warnings,
    )
    return [
        {
            "name": row[0],
            "principal_type": row[1] or "UNKNOWN",
            "login_name": row[2],
            "default_schema": row[3],
            "created_at": row[4],
            "modified_at": row[5],
            "authentication_type": row[6],
            "orphaned": bool(row[7]),
        }
        for row in rows
    ]


def _modern_server_permissions(cursor, warnings: list[str]) -> list[dict]:
    rows = _safe_rows(
        cursor,
        f"""
        SELECT TOP {MAX_PERMISSION_ROWS + 1}
            grantee.name,
            permission.state_desc,
            permission.permission_name,
            permission.class_desc,
            CASE
                WHEN permission.class_desc = 'SERVER' THEN @@SERVERNAME
                WHEN permission.class_desc = 'SERVER_PRINCIPAL' THEN target.name
                ELSE CAST(permission.major_id AS varchar(64))
            END,
            grantor.name
        FROM sys.server_permissions permission
        INNER JOIN sys.server_principals grantee
            ON grantee.principal_id = permission.grantee_principal_id
        LEFT JOIN sys.server_principals grantor
            ON grantor.principal_id = permission.grantor_principal_id
        LEFT JOIN sys.server_principals target
            ON permission.class_desc = 'SERVER_PRINCIPAL'
           AND target.principal_id = permission.major_id
        ORDER BY grantee.name, permission.permission_name
        """,
        "Direct server permissions could not be read.",
        warnings,
    )
    if len(rows) > MAX_PERMISSION_ROWS:
        warnings.append(
            f"Direct server permissions were capped at {MAX_PERMISSION_ROWS} rows."
        )
        rows = rows[:MAX_PERMISSION_ROWS]
    return [
        {
            "principal": row[0],
            "state": row[1],
            "permission": row[2],
            "scope": "server",
            "class_name": row[3],
            "securable": row[4],
            "grantor": row[5],
        }
        for row in rows
    ]


def _modern_database_permissions(cursor, warnings: list[str]) -> list[dict]:
    rows = _safe_rows(
        cursor,
        f"""
        SELECT TOP {MAX_PERMISSION_ROWS + 1}
            grantee.name,
            permission.state_desc,
            permission.permission_name,
            permission.class_desc,
            CASE
                WHEN permission.class_desc = 'DATABASE' THEN DB_NAME()
                WHEN permission.class_desc = 'OBJECT_OR_COLUMN' THEN
                    COALESCE(
                        QUOTENAME(OBJECT_SCHEMA_NAME(permission.major_id)) + '.' +
                        QUOTENAME(OBJECT_NAME(permission.major_id)),
                        CAST(permission.major_id AS varchar(64))
                    )
                WHEN permission.class_desc = 'SCHEMA' THEN
                    COALESCE(SCHEMA_NAME(permission.major_id), CAST(permission.major_id AS varchar(64)))
                WHEN permission.class_desc = 'DATABASE_PRINCIPAL' THEN target.name
                ELSE CAST(permission.major_id AS varchar(64))
            END,
            grantor.name
        FROM sys.database_permissions permission
        INNER JOIN sys.database_principals grantee
            ON grantee.principal_id = permission.grantee_principal_id
        LEFT JOIN sys.database_principals grantor
            ON grantor.principal_id = permission.grantor_principal_id
        LEFT JOIN sys.database_principals target
            ON permission.class_desc = 'DATABASE_PRINCIPAL'
           AND target.principal_id = permission.major_id
        ORDER BY grantee.name, permission.permission_name
        """,
        "Direct database permissions could not be read.",
        warnings,
    )
    if len(rows) > MAX_PERMISSION_ROWS:
        warnings.append(
            f"Direct database permissions were capped at {MAX_PERMISSION_ROWS} rows."
        )
        rows = rows[:MAX_PERMISSION_ROWS]
    return [
        {
            "principal": row[0],
            "state": row[1],
            "permission": row[2],
            "scope": "database",
            "class_name": row[3],
            "securable": row[4],
            "grantor": row[5],
        }
        for row in rows
    ]


def _legacy_database_permissions(cursor, warnings: list[str]) -> list[dict]:
    rows = _safe_rows(
        cursor,
        f"""
        SELECT TOP {MAX_PERMISSION_ROWS + 1}
            USER_NAME(protect.uid),
            protect.protecttype,
            protect.action,
            protect.id,
            CASE WHEN protect.id = 0 THEN DB_NAME() ELSE OBJECT_NAME(protect.id) END
        FROM dbo.sysprotects protect
        ORDER BY USER_NAME(protect.uid), protect.id, protect.action
        """,
        "Legacy database permissions could not be read.",
        warnings,
    )
    if len(rows) > MAX_PERMISSION_ROWS:
        warnings.append(
            f"Legacy database permissions were capped at {MAX_PERMISSION_ROWS} rows."
        )
        rows = rows[:MAX_PERMISSION_ROWS]
    return [
        {
            "principal": row[0] or "UNKNOWN",
            "state": LEGACY_PROTECT_TYPES.get(int(row[1]), f"LEGACY_{row[1]}"),
            "permission": LEGACY_PERMISSION_ACTIONS.get(int(row[2]), f"ACTION_{row[2]}"),
            "scope": "database",
            "class_name": "DATABASE" if int(row[3] or 0) == 0 else "OBJECT",
            "securable": row[4],
            "grantor": None,
        }
        for row in rows
    ]


def _attach_roles(principals: list[dict], memberships: list[dict]) -> None:
    by_principal: dict[str, list[str]] = {}
    for membership in memberships:
        principal = str(membership["principal"])
        by_principal.setdefault(principal.lower(), []).append(str(membership["role"]))
    for principal in principals:
        principal["roles"] = sorted(
            set(by_principal.get(str(principal["name"]).lower(), [])),
            key=str.lower,
        )


def _elevated_findings(
    server_roles: list[dict],
    database_roles: list[dict],
    server_permissions: list[dict],
    database_permissions: list[dict],
) -> list[dict]:
    findings: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    fixed_severity = dict(FIXED_SERVER_ROLES)
    for item in server_roles:
        role = str(item["role"])
        severity = fixed_severity.get(role.lower())
        if severity:
            key = (str(item["principal"]), "server_role", role)
            if key not in seen:
                seen.add(key)
                findings.append({
                    "principal": item["principal"],
                    "severity": severity,
                    "source": "Server role",
                    "detail": role,
                })

    for item in database_roles:
        role = str(item["role"])
        severity = ELEVATED_DATABASE_ROLES.get(role.lower())
        if severity:
            key = (str(item["principal"]), "database_role", role)
            if key not in seen:
                seen.add(key)
                findings.append({
                    "principal": item["principal"],
                    "severity": severity,
                    "source": "Database role",
                    "detail": role,
                })

    for item in server_permissions:
        permission = str(item["permission"]).upper()
        severity = ELEVATED_SERVER_PERMISSIONS.get(permission)
        if severity:
            detail = permission
            key = (str(item["principal"]), "server_permission", detail)
            if key not in seen:
                seen.add(key)
                findings.append({
                    "principal": item["principal"],
                    "severity": severity,
                    "source": "Server permission",
                    "detail": detail,
                })

    for item in database_permissions:
        permission = str(item["permission"]).upper()
        severity = ELEVATED_DATABASE_PERMISSIONS.get(permission)
        if severity and str(item["state"]).upper() != "DENY":
            detail = permission
            if item.get("securable"):
                detail += f" on {item['securable']}"
            key = (str(item["principal"]), "database_permission", detail)
            if key not in seen:
                seen.add(key)
                findings.append({
                    "principal": item["principal"],
                    "severity": severity,
                    "source": "Database permission",
                    "detail": detail,
                })

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        findings,
        key=lambda item: (
            severity_order.get(str(item["severity"]), 9),
            str(item["principal"]).lower(),
            str(item["detail"]).lower(),
        ),
    )


def _get_sqlserver_security_sync(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    warnings: list[str] = []

    try:
        with open_sqlserver_connection(connection) as db:
            identity = probe_sqlserver_identity(db)
            cursor = db.cursor()
            try:
                major = identity.version.major
                modern = bool(identity.capabilities.get("modern_catalog_views"))

                server_roles = _server_role_memberships_from_syslogins(cursor, warnings)
                if major is not None and major >= 11:
                    existing = {
                        (str(item["principal"]).lower(), str(item["role"]).lower())
                        for item in server_roles
                    }
                    for item in _modern_custom_server_roles(cursor, warnings):
                        key = (str(item["principal"]).lower(), str(item["role"]).lower())
                        if key not in existing:
                            existing.add(key)
                            server_roles.append(item)

                database_roles = _database_role_memberships(cursor, modern, warnings)

                if modern:
                    logins = _modern_logins(cursor, warnings)
                    users = _modern_database_users(cursor, major, warnings)
                    server_permissions = _modern_server_permissions(cursor, warnings)
                    database_permissions = _modern_database_permissions(cursor, warnings)
                else:
                    logins = _legacy_logins(cursor, warnings)
                    users = _legacy_database_users(cursor, warnings)
                    server_permissions = []
                    database_permissions = _legacy_database_permissions(cursor, warnings)
                    warnings.append(
                        "Legacy SQL Server security mode: fixed server roles and legacy database permissions are available, but granular server-permission metadata is not exposed by SQL Server 2000."
                    )

                _attach_roles(logins, server_roles)
                _attach_roles(users, database_roles)

                findings = _elevated_findings(
                    server_roles,
                    database_roles,
                    server_permissions,
                    database_permissions,
                )

                return {
                    "available": True,
                    "database_name": identity.database_name,
                    "generation": identity.version.generation,
                    "logins": logins,
                    "database_users": users,
                    "server_roles": server_roles,
                    "database_roles": database_roles,
                    "server_permissions": server_permissions,
                    "database_permissions": database_permissions,
                    "elevated_findings": findings,
                    "login_count": len(logins),
                    "database_user_count": len(users),
                    "disabled_login_count": sum(1 for item in logins if item["disabled"]),
                    "orphaned_user_count": sum(1 for item in users if item["orphaned"]),
                    "warnings": warnings,
                    "checked_at": checked_at,
                }
            finally:
                cursor.close()
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            sqlserver_error_message(exc),
            code="SQLSERVER_SECURITY_FAILED",
            status_code=400,
        ) from exc


async def get_sqlserver_security(connection: dict) -> dict:
    return await asyncio.to_thread(_get_sqlserver_security_sync, connection)
