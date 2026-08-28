from app.connectors.oracle_access_compare import _compare_access_payloads


def _source(kind="direct", via=None):
    return {
        "kind": kind,
        "via": via or [],
        "admin_option": False,
        "default_role": None,
        "grantable": None,
    }


def test_compare_access_splits_common_and_user_specific_access():
    left = {
        "username": "ALICE",
        "status": "OPEN",
        "profile": "DEFAULT",
        "default_tablespace": "USERS",
        "temporary_tablespace": "TEMP",
        "roles": [
            {"name": "APP_USER", "sources": [_source()], "powerful": False},
            {"name": "DBA", "sources": [_source()], "powerful": True},
        ],
        "system_privileges": [
            {"name": "CREATE SESSION", "sources": [_source()], "powerful": False},
            {
                "name": "SELECT ANY TABLE",
                "sources": [_source("role", ["DBA"])],
                "powerful": True,
            },
        ],
        "object_privileges": [
            {
                "owner": "APP",
                "object_name": "ORDERS",
                "privilege": "SELECT",
                "column_name": None,
                "sources": [_source()],
            }
        ],
        "administrative_privileges": ["SYSOPER"],
        "warnings": [],
    }
    right = {
        "username": "BOB",
        "status": "OPEN",
        "profile": "DEFAULT",
        "default_tablespace": "USERS",
        "temporary_tablespace": "TEMP",
        "roles": [
            {"name": "APP_USER", "sources": [_source("role", ["BASE_ROLE", "APP_USER"])], "powerful": False},
            {"name": "REPORTING", "sources": [_source()], "powerful": False},
        ],
        "system_privileges": [
            {"name": "CREATE SESSION", "sources": [_source()], "powerful": False},
        ],
        "object_privileges": [
            {
                "owner": "APP",
                "object_name": "ORDERS",
                "privilege": "SELECT",
                "column_name": None,
                "sources": [_source("role", ["APP_USER"])],
            },
            {
                "owner": "APP",
                "object_name": "CUSTOMERS",
                "privilege": "UPDATE",
                "column_name": "EMAIL",
                "sources": [_source()],
            },
        ],
        "administrative_privileges": [],
        "warnings": [],
    }

    result = _compare_access_payloads(left, right)

    assert [item["label"] for item in result["roles"]["common"]] == ["APP_USER"]
    assert [item["label"] for item in result["roles"]["left_only"]] == ["DBA"]
    assert [item["label"] for item in result["roles"]["right_only"]] == ["REPORTING"]
    assert result["roles"]["common"][0]["left_sources"][0]["kind"] == "direct"
    assert result["roles"]["common"][0]["right_sources"][0]["via"] == ["BASE_ROLE", "APP_USER"]

    assert [item["label"] for item in result["system_privileges"]["common"]] == ["CREATE SESSION"]
    assert result["system_privileges"]["left_only"][0]["label"] == "SELECT ANY TABLE"
    assert result["system_privileges"]["left_only"][0]["powerful"] is True

    assert result["object_privileges"]["common"][0]["label"] == "SELECT ON APP.ORDERS"
    assert result["object_privileges"]["right_only"][0]["label"] == "UPDATE ON APP.CUSTOMERS.EMAIL"
    assert result["administrative_privileges"]["left_only"][0]["label"] == "SYSOPER"

    assert result["common_count"] == 3
    assert result["left_only_count"] == 3
    assert result["right_only_count"] == 2


def test_compare_access_preserves_warnings_with_user_context():
    base = {
        "status": "OPEN",
        "profile": None,
        "default_tablespace": None,
        "temporary_tablespace": None,
        "roles": [],
        "system_privileges": [],
        "object_privileges": [],
        "administrative_privileges": [],
    }
    left = {**base, "username": "ALICE", "warnings": ["Object privileges unavailable"]}
    right = {**base, "username": "BOB", "warnings": ["Password file unavailable"]}

    result = _compare_access_payloads(left, right)

    assert result["warnings"] == [
        "ALICE: Object privileges unavailable",
        "BOB: Password file unavailable",
    ]
