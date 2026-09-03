from app.connectors.mysql_security import (
    _account_findings,
    _parse_grant,
    _redact_grant,
)


def test_grant_redaction_removes_auth_hash():
    raw = (
        "GRANT ALL PRIVILEGES ON *.* TO 'root'@'localhost' "
        "IDENTIFIED VIA mysql_native_password USING '*ABCDEF123456' "
        "WITH GRANT OPTION"
    )
    redacted = _redact_grant(raw)
    assert "*ABCDEF123456" not in redacted
    assert "[REDACTED]" in redacted


def test_parse_privileges_and_grant_option():
    privileges, roles, grant_option = _parse_grant(
        "GRANT SELECT, PROCESS ON *.* TO 'monitor'@'10.%' WITH GRANT OPTION"
    )
    assert roles == []
    assert grant_option is True
    assert {item["privilege"] for item in privileges} == {"SELECT", "PROCESS"}
    assert all(item["scope"] == "*.*" for item in privileges)


def test_parse_role_grant():
    privileges, roles, grant_option = _parse_grant(
        "GRANT `reporting_role` TO 'report'@'localhost'"
    )
    assert privileges == []
    assert roles == ["reporting_role"]
    assert grant_option is False


def test_remote_root_and_global_admin_grants_are_findings():
    account = {
        "user": "root",
        "host": "%",
        "account": "root@%",
        "privileges": [
            {"privilege": "SUPER", "scope": "*.*", "grant_option": False},
        ],
    }
    findings = _account_findings(account)
    assert any("Root is permitted" in item["detail"] for item in findings)
    assert any("SUPER" in item["detail"] for item in findings)
