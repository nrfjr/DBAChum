from app.connectors.oracle_access_lookup import (
    _build_role_paths_for_users,
    _normal_user_map,
    _object_matches,
    _privilege_matches,
    _role_matches,
)


def test_reverse_role_lookup_resolves_direct_and_inherited_users():
    users = {"ALICE": "OPEN", "BOB": "LOCKED"}
    role_names = {"APP_USER", "APP_READ", "REPORTING"}
    rows = [
        ("ALICE", "APP_USER", "NO", "YES"),
        ("BOB", "REPORTING", "NO", "YES"),
        ("APP_USER", "APP_READ", "NO", "YES"),
        ("REPORTING", "APP_READ", "NO", "YES"),
    ]
    paths = _build_role_paths_for_users(users, rows, role_names)
    matches = _role_matches(users, paths, "APP_READ")

    assert [item["username"] for item in matches] == ["ALICE", "BOB"]
    assert matches[0]["source"]["kind"] == "role"
    assert matches[0]["source"]["via"] == ["APP_USER", "APP_READ"]
    assert matches[1]["source"]["via"] == ["REPORTING", "APP_READ"]


def test_reverse_system_privilege_lookup_includes_direct_role_and_public_without_enumerating_public():
    users = {"ALICE": "OPEN", "BOB": "OPEN"}
    role_names = {"APP_USER"}
    paths = _build_role_paths_for_users(
        users,
        [
            ("ALICE", "APP_USER", "NO", "YES"),
        ],
        role_names,
    )
    matches, public = _privilege_matches(
        users=users,
        user_role_paths=paths,
        rows=[
            ("ALICE", "SELECT ANY TABLE", "NO"),
            ("APP_USER", "SELECT ANY TABLE", "NO"),
            ("PUBLIC", "SELECT ANY TABLE", "NO"),
        ],
        basis="SYSTEM PRIVILEGE",
    )

    assert public == ["SELECT ANY TABLE"]
    assert {item["username"] for item in matches} == {"ALICE"}
    assert {item["source"]["kind"] for item in matches} == {"direct", "role"}
    assert all(item["powerful"] is True for item in matches)


def test_object_lookup_combines_explicit_column_and_broad_any_access():
    users = {"ALICE": "OPEN", "BOB": "OPEN", "CAROL": "OPEN"}
    role_names = {"APP_READ"}
    paths = _build_role_paths_for_users(
        users,
        [
            ("BOB", "APP_READ", "NO", "YES"),
        ],
        role_names,
    )
    matches, public = _object_matches(
        users=users,
        user_role_paths=paths,
        table_rows=[
            ("ALICE", "SELECT", "NO"),
            ("PUBLIC", "SELECT", "NO"),
        ],
        column_rows=[
            ("APP_READ", "UPDATE", "EMAIL", "NO"),
        ],
        system_rows=[
            ("CAROL", "SELECT ANY TABLE", "NO"),
        ],
    )

    assert public == ["SELECT (object)"]
    by_user = {name: [item for item in matches if item["username"] == name] for name in users}
    assert any(item["basis"] == "OBJECT PRIVILEGE" for item in by_user["ALICE"])
    assert any(item["basis"] == "COLUMN PRIVILEGE" and item["column_name"] == "EMAIL" for item in by_user["BOB"])
    assert any(item["basis"] == "SYSTEM PRIVILEGE" and item["privilege"] == "SELECT ANY TABLE" for item in by_user["CAROL"])


def test_user_filter_hides_oracle_maintained_and_known_system_accounts():
    rows = [
        ("APPUSER", "OPEN", "N"),
        ("SYS", "OPEN", "Y"),
        ("SYSTEM", "OPEN", "N"),
        ("ORACLE_OWNED", "OPEN", "Y"),
    ]
    assert _normal_user_map(rows, True) == {"APPUSER": "OPEN"}
