from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

from app.connectors import oracle_provisioning
from app.core.exceptions import AppError
from app.schemas.oracle_dba import OracleCreateUserRequest
from app.schemas.user import UserResponse, UserRole
from app.services import oracle_dba


class FakeReferenceConnection:
    async def fetchone(self, sql, parameters=None):
        assert parameters == {"username": "APP_USER"}
        if "FROM dba_users" in sql:
            return (
                "APP_USER",
                "OPEN",
                "USERS",
                "TEMP",
                "DEFAULT",
            )
        raise AssertionError(sql)

    async def fetchall(self, sql, parameters=None):
        assert parameters == {"username": "APP_USER"}
        if "FROM dba_role_privs" in sql:
            return [
                ("APP_READ", "NO", "YES"),
                ("DBA", "YES", "YES"),
            ]
        if "FROM dba_sys_privs" in sql:
            return [
                ("CREATE SESSION", "NO"),
            ]
        raise AssertionError(sql)


class FakeCreateConnection:
    def __init__(self):
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)


@pytest.mark.asyncio
async def test_reference_user_preview_separates_roles_and_system_privileges(
    monkeypatch,
):
    fake_connection = FakeReferenceConnection()

    @asynccontextmanager
    async def fake_open(_connection):
        yield fake_connection

    monkeypatch.setattr(
        oracle_provisioning,
        "open_oracle_connection",
        fake_open,
    )

    result = await oracle_provisioning.get_oracle_reference_user(
        {"engine": "oracle"},
        "app_user",
    )

    assert result["username"] == "APP_USER"
    assert result["default_tablespace"] == "USERS"
    assert result["roles"][0]["name"] == "APP_READ"
    assert result["roles"][0]["sensitive"] is False
    assert result["roles"][1]["name"] == "DBA"
    assert result["roles"][1]["sensitive"] is True
    assert result["system_privileges"] == [
        {
            "name": "CREATE SESSION",
            "admin_option": False,
        }
    ]


@pytest.mark.asyncio
async def test_create_oracle_user_builds_reviewed_ddl(
    monkeypatch,
):
    fake_connection = FakeCreateConnection()

    @asynccontextmanager
    async def fake_open(_connection):
        yield fake_connection

    monkeypatch.setattr(
        oracle_provisioning,
        "open_oracle_connection",
        fake_open,
    )

    result = await oracle_provisioning.create_oracle_user(
        {"engine": "oracle"},
        username="jsmith1001",
        password="abc12345",
        roles=["app_read"],
        default_tablespace="users",
        temporary_tablespace="temp",
        profile="default",
    )

    assert fake_connection.statements[0] == (
        'CREATE USER "JSMITH1001" IDENTIFIED BY "abc12345" '
        'DEFAULT TABLESPACE "USERS" TEMPORARY TABLESPACE "TEMP" '
        'PROFILE "DEFAULT"'
    )
    assert fake_connection.statements[1] == (
        'GRANT "APP_READ" TO "JSMITH1001"'
    )
    assert result["roles_applied"] == ["APP_READ"]


def make_operator():
    now = datetime.now(timezone.utc)
    return UserResponse(
        id="operator-1",
        username="dba01",
        display_name="DBA 01",
        role=UserRole.OPERATOR,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_provisioning_audits_success_without_password(
    monkeypatch,
):
    connection = {
        "engine": "oracle",
        "oracle_auth_mode": "sysdba",
    }
    audit_started = {}
    audit_finished = {}

    async def fake_target(_database, _connection_id):
        return connection

    async def fake_exists(_connection, _username):
        return False

    async def fake_reference(_connection, _username):
        return {
            "username": "APP_USER",
            "default_tablespace": "USERS",
            "temporary_tablespace": "TEMP",
            "profile": "DEFAULT",
            "roles": [
                {
                    "name": "APP_READ",
                    "sensitive": False,
                }
            ],
        }

    async def fake_start(_database, **kwargs):
        audit_started.update(kwargs)
        return "audit-1"

    async def fake_create(_connection, **kwargs):
        assert kwargs["password"] == "abc12345"
        return {
            "roles_applied": ["APP_READ"],
            "default_tablespace": "USERS",
            "temporary_tablespace": "TEMP",
            "profile": "DEFAULT",
        }

    async def fake_finish(_database, audit_id, **kwargs):
        audit_finished["audit_id"] = audit_id
        audit_finished.update(kwargs)
        return None

    monkeypatch.setattr(oracle_dba, "get_oracle_target", fake_target)
    monkeypatch.setattr(oracle_dba, "oracle_user_exists", fake_exists)
    monkeypatch.setattr(oracle_dba, "get_oracle_reference_user", fake_reference)
    monkeypatch.setattr(oracle_dba, "start_database_action", fake_start)
    monkeypatch.setattr(oracle_dba, "create_oracle_user", fake_create)
    monkeypatch.setattr(oracle_dba, "finish_database_action", fake_finish)

    result = await oracle_dba.provision_oracle_user(
        object(),
        "conn-1",
        OracleCreateUserRequest(
            username="JSMITH1001",
            password="abc12345",
            reference_username="APP_USER",
            roles=["APP_READ"],
            request_reference="REQ-123",
            requestor_name="Requestor",
        ),
        make_operator(),
    )

    assert result["status"] == "succeeded"
    assert audit_started["action"] == "create_user"
    assert audit_started["target"] == "JSMITH1001"
    assert audit_started["details"]["connection_auth_mode"] == "sysdba"
    assert "password" not in audit_started["details"]
    assert audit_finished["audit_id"] == "audit-1"
    assert audit_finished["after"]["exists"] is True


@pytest.mark.asyncio
async def test_provisioning_blocks_sensitive_reference_roles(
    monkeypatch,
):
    async def fake_target(_database, _connection_id):
        return {"engine": "oracle"}

    async def fake_exists(_connection, _username):
        return False

    async def fake_reference(_connection, _username):
        return {
            "username": "APP_USER",
            "default_tablespace": "USERS",
            "temporary_tablespace": "TEMP",
            "profile": "DEFAULT",
            "roles": [
                {
                    "name": "DBA",
                    "sensitive": True,
                }
            ],
        }

    monkeypatch.setattr(oracle_dba, "get_oracle_target", fake_target)
    monkeypatch.setattr(oracle_dba, "oracle_user_exists", fake_exists)
    monkeypatch.setattr(oracle_dba, "get_oracle_reference_user", fake_reference)

    with pytest.raises(AppError) as exc_info:
        await oracle_dba.provision_oracle_user(
            object(),
            "conn-1",
            OracleCreateUserRequest(
                username="JSMITH1001",
                password="abc12345",
                reference_username="APP_USER",
                roles=["DBA"],
            ),
            make_operator(),
        )

    assert exc_info.value.code == "ORACLE_SENSITIVE_ROLE_BLOCKED"
