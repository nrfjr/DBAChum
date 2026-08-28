from contextlib import asynccontextmanager

import pytest

from app.connectors import oracle_role_management as roles
from app.core.exceptions import AppError


def test_legacy_role_protection_keeps_oracle_supplied_roles_inspect_only():
    assert roles._role_protection("DBA", False)["manageable"] is False
    assert roles._role_protection("CONNECT", False)["manageable"] is False
    assert roles._role_protection("APP_CUSTOM_ROLE", False)["manageable"] is True
    assert roles._role_protection("APP_CUSTOM_ROLE", True)["manageable"] is False


def test_role_graph_cycle_detection_is_version_neutral():
    edges = {
        "APP_A": {"APP_B"},
        "APP_B": {"APP_C"},
        "APP_C": set(),
    }
    assert roles._graph_reaches(edges, "APP_A", "APP_C") is True
    assert roles._graph_reaches(edges, "APP_C", "APP_A") is False


def test_privilege_normalization_rejects_sql_punctuation():
    assert roles.normalize_privilege(" select any table ") == "SELECT ANY TABLE"
    with pytest.raises(AppError):
        roles.normalize_privilege("SELECT ANY TABLE; DROP USER X")


@pytest.mark.asyncio
async def test_system_privilege_preview_builds_exact_statement_and_flags_elevated(monkeypatch):
    class FakeConnection:
        async def fetchone(self, sql, parameters=None):
            if "dba_sys_privs" in sql.lower():
                return None
            raise AssertionError(sql)

    @asynccontextmanager
    async def fake_open(_connection):
        yield FakeConnection()

    async def fake_role_meta(_connection, role_name):
        return {
            "name": role_name,
            "protected": False,
            "powerful": False,
            "manageable": True,
        }

    async def fake_sys_catalog(_connection):
        return ["CREATE SESSION", "SELECT ANY TABLE"], None

    monkeypatch.setattr(roles, "open_oracle_connection", fake_open)
    monkeypatch.setattr(roles, "_get_role_metadata", fake_role_meta)
    monkeypatch.setattr(roles, "_catalog_system_privileges", fake_sys_catalog)

    preview = await roles.build_oracle_role_change_preview(
        {},
        "APP_REPORT",
        operation="grant_system_privilege",
        privilege="select any table",
    )

    assert preview["statement"] == 'GRANT SELECT ANY TABLE TO "APP_REPORT"'
    assert preview["ready_to_execute"] is True
    assert preview["powerful"] is True
    assert any("elevated" in warning.lower() for warning in preview["warnings"])


@pytest.mark.asyncio
async def test_protected_child_role_cannot_be_added_to_custom_role(monkeypatch):
    class FakeConnection:
        async def fetchone(self, sql, parameters=None):
            if "dba_role_privs" in sql.lower():
                return None
            raise AssertionError(sql)

    @asynccontextmanager
    async def fake_open(_connection):
        yield FakeConnection()

    async def fake_role_meta(_connection, role_name):
        if role_name == "DBA":
            return {
                "name": "DBA",
                "protected": True,
                "powerful": True,
                "manageable": False,
            }
        return {
            "name": role_name,
            "protected": False,
            "powerful": False,
            "manageable": True,
        }

    monkeypatch.setattr(roles, "open_oracle_connection", fake_open)
    monkeypatch.setattr(roles, "_get_role_metadata", fake_role_meta)

    with pytest.raises(AppError) as caught:
        await roles.build_oracle_role_change_preview(
            {},
            "APP_REPORT",
            operation="grant_child_role",
            value="DBA",
        )

    assert caught.value.code == "ORACLE_PROTECTED_CHILD_ROLE_ADD_BLOCKED"
