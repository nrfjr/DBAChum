from app.connectors.oracle_access_inspector import (
    _aggregate_access,
    _build_role_paths,
    _is_powerful_system_privilege,
)


def test_role_paths_resolve_direct_and_inherited_roles_without_recursive_sql():
    direct = [
        ("APP_USER", "NO", "YES"),
        ("REPORTING", "YES", "NO"),
    ]
    hierarchy = [
        ("APP_USER", "APP_READ", "NO", "YES"),
        ("APP_READ", "APP_BASE", "NO", "YES"),
        ("APP_BASE", "APP_USER", "NO", "YES"),  # cycle must not loop
    ]

    paths = _build_role_paths(direct, hierarchy)

    assert paths["APP_USER"]["direct"] is True
    assert paths["APP_USER"]["default_role"] is True
    assert paths["REPORTING"]["admin_option"] is True
    assert paths["APP_READ"]["path"] == ["APP_USER", "APP_READ"]
    assert paths["APP_BASE"]["path"] == ["APP_USER", "APP_READ", "APP_BASE"]


def test_access_aggregation_distinguishes_direct_role_public_and_inherited_sources():
    result = _aggregate_access(
        username="APPUSER",
        direct_role_rows=[("APP_USER", "NO", "YES")],
        role_grant_rows=[("APP_USER", "APP_READ", "NO", "YES")],
        system_privilege_rows=[
            ("APPUSER", "CREATE SESSION", "NO"),
            ("APP_READ", "SELECT ANY TABLE", "NO"),
            ("PUBLIC", "CREATE SYNONYM", "NO"),
        ],
        object_privilege_rows=[
            ("APPUSER", "APP", "ORDERS", "SELECT", "YES"),
            ("APP_READ", "APP", "CUSTOMERS", "SELECT", "NO"),
            ("PUBLIC", "SYS", "DUAL", "SELECT", "NO"),
        ],
        column_privilege_rows=[
            ("APP_READ", "APP", "CUSTOMERS", "EMAIL", "UPDATE", "NO"),
        ],
        administrative_privileges=["SYSOPER"],
    )

    roles = {item["name"]: item for item in result["roles"]}
    assert roles["APP_USER"]["sources"][0]["kind"] == "direct"
    assert roles["APP_READ"]["sources"][0]["kind"] == "role"
    assert roles["APP_READ"]["sources"][0]["via"] == ["APP_USER", "APP_READ"]

    sys_privs = {item["name"]: item for item in result["system_privileges"]}
    assert sys_privs["CREATE SESSION"]["sources"][0]["kind"] == "direct"
    assert sys_privs["SELECT ANY TABLE"]["powerful"] is True
    assert sys_privs["SELECT ANY TABLE"]["sources"][0]["via"] == ["APP_USER", "APP_READ"]
    assert sys_privs["CREATE SYNONYM"]["sources"][0]["kind"] == "public"

    object_privs = {
        (item["owner"], item["object_name"], item["column_name"], item["privilege"]): item
        for item in result["object_privileges"]
    }
    direct = object_privs[("APP", "ORDERS", None, "SELECT")]
    assert direct["sources"][0]["kind"] == "direct"
    assert direct["sources"][0]["grantable"] is True

    inherited = object_privs[("APP", "CUSTOMERS", None, "SELECT")]
    assert inherited["sources"][0]["kind"] == "role"
    column = object_privs[("APP", "CUSTOMERS", "EMAIL", "UPDATE")]
    assert column["sources"][0]["via"] == ["APP_USER", "APP_READ"]

    findings = {(item["kind"], item["name"]) for item in result["powerful_findings"]}
    assert ("system_privilege", "SELECT ANY TABLE") in findings
    assert ("administrative_privilege", "SYSOPER") in findings


def test_powerful_privilege_rule_catches_curated_and_broad_any_privileges():
    assert _is_powerful_system_privilege("ALTER SYSTEM") is True
    assert _is_powerful_system_privilege("CREATE ANY INDEX") is True
    assert _is_powerful_system_privilege("CREATE SESSION") is False
