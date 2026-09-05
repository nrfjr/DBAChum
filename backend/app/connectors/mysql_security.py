import asyncio
import re
from datetime import datetime, timezone

import mysql.connector as mysql_connector
from mysql.connector import Error as MySQLError

from app.connectors.mysql import (
    _close_mysql_resource,
    _read_mysql_identity,
    mysql_connect_kwargs,
    probe_mysql_capabilities,
)
from app.core.exceptions import AppError


MAX_ACCOUNTS = 200
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
HIGH_RISK_PRIVILEGES = {
    "ALL PRIVILEGES",
    "SUPER",
    "FILE",
    "SHUTDOWN",
    "CREATE USER",
    "SYSTEM_USER",
    "SYSTEM_VARIABLES_ADMIN",
    "ROLE_ADMIN",
    "CONNECTION_ADMIN",
}
REVIEW_PRIVILEGES = {
    "RELOAD",
    "PROCESS",
    "REPLICATION SLAVE",
    "REPLICATION CLIENT",
    "REPLICATION REPLICA",
}


def _boolish(value) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if normalized in {"Y", "YES", "ON", "1", "TRUE"}:
        return True
    if normalized in {"N", "NO", "OFF", "0", "FALSE"}:
        return False
    return None


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _redact_grant(statement: str) -> str:
    value = statement
    patterns = [
        (r"(?i)(IDENTIFIED\s+BY\s+PASSWORD\s+)'(?:''|[^'])*'", r"\1'[REDACTED]'"),
        (r"(?i)(IDENTIFIED\s+BY\s+)'(?:''|[^'])*'", r"\1'[REDACTED]'"),
        (r"(?i)(\bUSING\s+)'(?:''|[^'])*'", r"\1'[REDACTED]'"),
        (r"(?i)(\bAS\s+)'(?:''|[^'])*'", r"\1'[REDACTED]'"),
    ]
    for pattern, replacement in patterns:
        value = re.sub(pattern, replacement, value)
    return value


def _strip_identifier(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"`", "'", '"'}:
        return value[1:-1].replace(value[0] * 2, value[0])
    return value


def _parse_grant(statement: str) -> tuple[list[dict], list[str], bool]:
    privileges: list[dict] = []
    roles: list[str] = []
    with_grant_option = bool(re.search(r"(?i)\bWITH\s+GRANT\s+OPTION\b", statement))

    match = re.search(
        r"(?is)^\s*GRANT\s+(.*?)\s+ON\s+(.*?)\s+TO\s+",
        statement,
    )
    if match:
        scope = match.group(2).strip()
        for privilege in match.group(1).split(","):
            name = re.sub(r"\s+", " ", privilege.strip()).upper()
            if not name or name == "USAGE":
                continue
            privileges.append(
                {
                    "privilege": name,
                    "scope": scope,
                    "grant_option": with_grant_option,
                }
            )
        return privileges, roles, with_grant_option

    role_match = re.search(r"(?is)^\s*GRANT\s+(.*?)\s+TO\s+", statement)
    if role_match:
        role_text = role_match.group(1).strip()
        for role in role_text.split(","):
            cleaned = _strip_identifier(role.strip())
            if cleaned and not cleaned.upper().startswith(("USAGE", "PROXY")):
                roles.append(cleaned)

    return privileges, roles, with_grant_option


def _account_findings(account: dict) -> list[dict]:
    findings: list[dict] = []
    user = account["user"]
    host = account["host"]
    principal = account["account"]

    if not user:
        findings.append(
            {
                "principal": principal,
                "severity": "high",
                "source": "account",
                "detail": "Anonymous database account is present.",
            }
        )

    if user.lower() == "root" and host.lower() not in LOCAL_HOSTS:
        findings.append(
            {
                "principal": principal,
                "severity": "critical",
                "source": "account",
                "detail": f"Root is permitted from remote host pattern {host}.",
            }
        )

    if "%" in host or "_" in host:
        findings.append(
            {
                "principal": principal,
                "severity": "warning",
                "source": "host",
                "detail": f"Account uses wildcard host pattern {host}.",
            }
        )

    for item in account.get("privileges", []):
        privilege = item["privilege"].upper()
        scope = item["scope"]

        if privilege in HIGH_RISK_PRIVILEGES:
            findings.append(
                {
                    "principal": principal,
                    "severity": "critical" if scope == "*.*" else "high",
                    "source": "privilege",
                    "detail": f"{privilege} on {scope}.",
                }
            )
        elif privilege in REVIEW_PRIVILEGES and scope == "*.*":
            findings.append(
                {
                    "principal": principal,
                    "severity": "warning",
                    "source": "privilege",
                    "detail": f"Global {privilege} privilege.",
                }
            )

        if item.get("grant_option"):
            findings.append(
                {
                    "principal": principal,
                    "severity": "critical" if scope == "*.*" else "high",
                    "source": "grant option",
                    "detail": f"Can grant privileges on {scope} to other accounts.",
                }
            )

    return findings


def _parse_grantee(value: str) -> tuple[str, str] | None:
    match = re.match(r"^'((?:''|[^'])*)'@'((?:''|[^'])*)'$", str(value).strip())
    if not match:
        return None
    return match.group(1).replace("''", "'"), match.group(2).replace("''", "'")


def _mysql_user_columns(cursor) -> set[str]:
    try:
        cursor.execute(
            """
            SELECT LOWER(column_name)
            FROM information_schema.columns
            WHERE LOWER(table_schema) = 'mysql'
              AND LOWER(table_name) = 'user'
            """
        )
        return {str(row[0]).lower() for row in cursor.fetchall()}
    except MySQLError:
        return set()


def _accounts_from_mysql_user(cursor) -> tuple[list[dict], str] | None:
    columns = _mysql_user_columns(cursor)
    if not {"user", "host"}.issubset(columns):
        return None

    optional = [
        "plugin",
        "account_locked",
        "password_expired",
        "is_role",
        "default_role",
        "ssl_type",
        "password_last_changed",
    ]
    selected = ["User", "Host"] + [name for name in optional if name.lower() in columns]

    try:
        cursor.execute(
            "SELECT " + ", ".join(f"`{name}`" for name in selected) +
            " FROM mysql.user ORDER BY User, Host LIMIT " + str(MAX_ACCOUNTS + 1)
        )
        rows = cursor.fetchall()
    except MySQLError:
        return None

    accounts: list[dict] = []
    for row in rows[:MAX_ACCOUNTS]:
        values = dict(zip(selected, row))
        accounts.append(
            {
                "user": str(values.get("User") or ""),
                "host": str(values.get("Host") or ""),
                "auth_plugin": values.get("plugin"),
                "account_locked": _boolish(values.get("account_locked")),
                "password_expired": _boolish(values.get("password_expired")),
                "is_role": _boolish(values.get("is_role")) or False,
                "default_role": values.get("default_role"),
                "ssl_type": values.get("ssl_type"),
                "password_last_changed": values.get("password_last_changed"),
            }
        )

    return accounts, "mysql.user" + (" (truncated)" if len(rows) > MAX_ACCOUNTS else "")


def _accounts_from_information_schema(cursor) -> tuple[list[dict], str] | None:
    grantees: set[tuple[str, str]] = set()
    sources = [
        "USER_PRIVILEGES",
        "SCHEMA_PRIVILEGES",
        "TABLE_PRIVILEGES",
        "ROUTINE_PRIVILEGES",
    ]

    for source in sources:
        try:
            cursor.execute(
                f"SELECT DISTINCT GRANTEE FROM information_schema.{source} LIMIT {MAX_ACCOUNTS + 1}"
            )
            for row in cursor.fetchall():
                parsed = _parse_grantee(row[0]) if row else None
                if parsed:
                    grantees.add(parsed)
        except MySQLError:
            continue

    if not grantees:
        return None

    accounts = [
        {
            "user": user,
            "host": host,
            "auth_plugin": None,
            "account_locked": None,
            "password_expired": None,
            "is_role": False,
            "default_role": None,
            "ssl_type": None,
            "password_last_changed": None,
        }
        for user, host in sorted(grantees)[:MAX_ACCOUNTS]
    ]
    return accounts, "information_schema privilege views"


def _current_account(cursor) -> tuple[str, str, str | None]:
    cursor.execute("SELECT CURRENT_USER(), USER()")
    row = cursor.fetchone()
    current = str(row[0] or "") if row else ""
    login_identity = str(row[1] or "") if row else None
    if "@" in current:
        user, host = current.rsplit("@", 1)
    else:
        user, host = current, ""
    return user, host, login_identity


def _show_grants(cursor, user: str, host: str, current: bool) -> tuple[list[str], bool]:
    try:
        if current:
            cursor.execute("SHOW GRANTS")
        else:
            cursor.execute(
                f"SHOW GRANTS FOR {_sql_literal(user)}@{_sql_literal(host)}"
            )
        rows = cursor.fetchall()
        statements = [_redact_grant(str(row[0])) for row in rows if row]
        return statements, True
    except MySQLError:
        return [], False


def _get_mysql_security_sync(connection: dict) -> dict:
    checked_at = datetime.now(timezone.utc)
    mysql_connection = None
    cursor = None

    try:
        mysql_connection = mysql_connector.connect(**mysql_connect_kwargs(connection))
        cursor = mysql_connection.cursor()

        identity = _read_mysql_identity(cursor)
        capabilities = probe_mysql_capabilities(cursor, identity["version_info"])
        current_user, current_host, login_identity = _current_account(cursor)

        warnings: list[str] = []
        fetched = _accounts_from_mysql_user(cursor)
        complete_account_list = bool(
            fetched is not None and not fetched[1].endswith('(truncated)')
        )

        if fetched is None:
            fetched = _accounts_from_information_schema(cursor)
            if fetched is not None:
                warnings.append(
                    "mysql.user is not readable by this login. Account discovery is based on "
                    "visible INFORMATION_SCHEMA privilege rows and may omit accounts with no visible grants."
                )

        if fetched is None:
            accounts = [
                {
                    "user": current_user,
                    "host": current_host,
                    "auth_plugin": None,
                    "account_locked": None,
                    "password_expired": None,
                    "is_role": False,
                    "default_role": None,
                    "ssl_type": None,
                    "password_last_changed": None,
                }
            ]
            metadata_source = "CURRENT_USER()"
            warnings.append(
                "Account enumeration is not permitted for this login; DBAChum can inspect only the connected identity."
            )
        else:
            accounts, metadata_source = fetched

        if not any(
            item["user"] == current_user and item["host"] == current_host
            for item in accounts
        ):
            accounts.insert(
                0,
                {
                    "user": current_user,
                    "host": current_host,
                    "auth_plugin": None,
                    "account_locked": None,
                    "password_expired": None,
                    "is_role": False,
                    "default_role": None,
                    "ssl_type": None,
                    "password_last_changed": None,
                },
            )

        grant_visibility_limited = False
        enriched: list[dict] = []
        all_findings: list[dict] = []

        for raw in accounts[:MAX_ACCOUNTS]:
            user = raw["user"]
            host = raw["host"]
            current = user == current_user and host == current_host
            statements, grants_visible = _show_grants(cursor, user, host, current)

            privileges: list[dict] = []
            roles: list[str] = []
            for statement in statements:
                parsed_privileges, parsed_roles, _ = _parse_grant(statement)
                privileges.extend(parsed_privileges)
                roles.extend(parsed_roles)

            roles = list(dict.fromkeys(roles))
            unique_privileges: list[dict] = []
            seen_privileges: set[tuple] = set()
            for item in privileges:
                key = (item["privilege"], item["scope"], item["grant_option"])
                if key not in seen_privileges:
                    seen_privileges.add(key)
                    unique_privileges.append(item)

            account = {
                **raw,
                "account": f"{user or '<anonymous>'}@{host}",
                "current_identity": current,
                "login_identity": login_identity if current else None,
                "wildcard_host": "%" in host or "_" in host,
                "remote_host": host.lower() not in LOCAL_HOSTS,
                "grants_visible": grants_visible,
                "grants": statements,
                "roles": roles,
                "privileges": unique_privileges,
            }
            findings = _account_findings(account)
            account["elevated_findings"] = findings
            all_findings.extend(findings)
            enriched.append(account)

            if not grants_visible and not current:
                grant_visibility_limited = True

        if grant_visibility_limited:
            warnings.append(
                "SHOW GRANTS is not permitted for one or more accounts. Those accounts remain listed, but their roles and privileges are incomplete."
            )

        if len(accounts) > MAX_ACCOUNTS or metadata_source.endswith("(truncated)"):
            warnings.append(
                f"Account inventory is limited to the first {MAX_ACCOUNTS} visible accounts."
            )

        if capabilities.get("mariadb_global_priv"):
            warnings.append(
                "MariaDB global_priv storage was detected. DBAChum intentionally reads the mysql.user compatibility surface and SHOW GRANTS, and never returns password/authentication hashes."
            )

        return {
            "available": True,
            "database_name": connection.get("database") or identity["database_name"],
            "scope": "instance",
            "product": identity["version_info"].product_name,
            "generation": identity["version_info"].generation,
            "metadata_source": metadata_source,
            "grants_source": "SHOW GRANTS",
            "complete_account_list": complete_account_list,
            "account_count": len(enriched),
            "anonymous_account_count": sum(1 for item in enriched if not item["user"]),
            "wildcard_host_count": sum(1 for item in enriched if item["wildcard_host"]),
            "role_account_count": sum(1 for item in enriched if item["is_role"]),
            "accounts": enriched,
            "elevated_findings": all_findings,
            "warnings": warnings,
            "checked_at": checked_at,
        }
    finally:
        _close_mysql_resource(cursor)
        _close_mysql_resource(mysql_connection)


async def get_mysql_security(connection: dict) -> dict:
    try:
        return await asyncio.to_thread(_get_mysql_security_sync, connection)
    except AppError:
        raise
    except (MySQLError, TypeError, ValueError, OSError) as exc:
        raise AppError(
            str(exc),
            code="MYSQL_SECURITY_FAILED",
            status_code=400,
        ) from exc
