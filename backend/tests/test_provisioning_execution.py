from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.core.exceptions import AppError
from app.schemas.provisioning import (
    ProvisioningExecuteRequest,
    ProvisioningPreviewLdap,
    ProvisioningPreviewResponse,
)
from app.schemas.user import UserResponse, UserRole
from app.services import provisioning_execution


PROFILE_ID = "a" * 24
PARENT_ID = "b" * 24
STEP_ID = "c" * 24


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeRuns:
    def __init__(self):
        self.inserted = []
        self.updates = []

    async def insert_one(self, document):
        self.inserted.append(document)
        return FakeInsertResult(ObjectId())

    async def update_one(self, query, update):
        self.updates.append((query, update))


class FakeDatabase:
    def __init__(self):
        self.provisioning_runs = FakeRuns()


def operator():
    return UserResponse(
        id="admin-1",
        username="meimei",
        display_name="DBA",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


def execute_request():
    return ProvisioningExecuteRequest(
        username="JPNINO12345",
        password="abc12345",
        first_name="José",
        middle_name="Peña",
        last_name="Niño",
        employee_id="12-345",
        reference_user="APP_USER",
        requestor="DBA Requestor",
        request_reference="REQ-123",
        remarks="RMS access",
        roles=["APP_READ"],
        default_tablespace="USERS",
        temporary_tablespace="TEMP",
        oracle_profile="DEFAULT",
    )


def preview():
    return ProvisioningPreviewResponse(
        dry_run=True,
        ready_to_execute=True,
        profile_id=PROFILE_ID,
        profile_name="ORMS",
        schema_connection_id=PARENT_ID,
        schema_connection_name="RMSUAT SYS",
        username="JPNINO12345",
        account_exists=False,
        account_action="create",
        requester_ip="192.0.2.25",
        operator_username="meimei",
        generated_at=datetime.now(timezone.utc),
        reference_user="APP_USER",
        ldap=ProvisioningPreviewLdap(enabled=True, profile_id="global", profile_name="LDAP", filename="JPNINO12345.ldif", template_valid=True),
    )


@pytest.mark.asyncio
async def test_execute_provisioning_creates_parent_upserts_step_and_adds_ldap_entry(monkeypatch):
    database = FakeDatabase()
    profile = {
        "_id": ObjectId(PROFILE_ID),
        "name": "ORMS",
        "schema_connection_id": PARENT_ID,
        "ldap_enabled": True,
        "ldap_profile_id": "global",
        "updated_at": datetime.now(timezone.utc),
        "table_steps": [{
            "name": "USER_MASTER",
            "connection_id": STEP_ID,
            "owner": "ORMS",
            "table_name": "USER_MASTER",
            "match_columns": ["USERNAME"],
            "mappings": [
                {"column_name": "ID", "value_kind": "sequence", "value_key": "USER_MASTER_SEQ"},
                {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
                {"column_name": "PASSWORD", "value_kind": "generated", "value_key": "password"},
                {"column_name": "CREATED_BY", "value_kind": "generated", "value_key": "requester_ip"},
            ],
        }],
    }

    async def fake_preview(*_args, **_kwargs):
        return preview()

    async def fake_profile(_database, _profile_id):
        return profile

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "RMSUAT SYS" if connection_id == PARENT_ID else "ORMS APP", "engine": "oracle", "active": True}

    async def fake_reference(_connection, _username):
        return {"username": "APP_USER", "roles": [{"name": "APP_READ", "sensitive": False}]}

    async def fake_reconcile(*_args, **_kwargs):
        return {
            "account_action": "created",
            "password_applied": True,
            "roles_added": ["APP_READ"],
            "roles_already_present": [],
            "default_tablespace": "USERS",
            "temporary_tablespace": "TEMP",
            "profile": "DEFAULT",
        }

    captured = {}

    async def fake_upsert(_connection, **kwargs):
        captured.update(kwargs)
        return {"action": "inserted", "existing_rows": 0, "rowcount": 1, "generated_values": {"ID": 77}}

    async def fake_ldap(_database, _profile_id):
        return {"name": "LDAP", "base_dn": "dc=example,dc=com", "ldif_template": "dn: uid=<USERNAME>,<BASE_DN>\nuserPassword: <PASSWORD>"}

    async def fake_ldap_add(_profile, content):
        assert "abc12345" in content
        return {"action": "created", "dn": "uid=JPNINO12345,dc=example,dc=com"}

    async def fake_start(*_args, **_kwargs):
        return "audit-1"

    async def fake_finish(*_args, **_kwargs):
        return None

    monkeypatch.setattr(provisioning_execution, "build_provisioning_preview", fake_preview)
    monkeypatch.setattr(provisioning_execution, "get_provisioning_profile", fake_profile)
    monkeypatch.setattr(provisioning_execution, "get_database_connection", fake_connection)
    monkeypatch.setattr(provisioning_execution, "get_oracle_reference_user", fake_reference)
    monkeypatch.setattr(provisioning_execution, "reconcile_oracle_user", fake_reconcile)
    monkeypatch.setattr(provisioning_execution, "upsert_oracle_provisioning_row", fake_upsert)
    monkeypatch.setattr(provisioning_execution, "get_ldap_profile_document", fake_ldap)
    monkeypatch.setattr(provisioning_execution, "add_ldap_entry_from_ldif", fake_ldap_add)
    monkeypatch.setattr(provisioning_execution, "start_database_action", fake_start)
    monkeypatch.setattr(provisioning_execution, "finish_database_action", fake_finish)

    result = await provisioning_execution.execute_provisioning_profile(
        database,
        PARENT_ID,
        PROFILE_ID,
        execute_request(),
        operator(),
        requester_ip="192.0.2.25",
    )

    assert result.status == "succeeded"
    assert result.account.action == "created"
    assert result.roles[0].action == "granted"
    assert result.table_steps[0].action == "inserted"
    assert result.table_steps[0].generated_values == {"ID": "77"}
    assert result.ldap.action == "created"
    assert "abc12345" in result.ldap.content
    assert captured["match_values"] == {"USERNAME": "JPNINO12345"}
    assert captured["sequence_columns"] == {"ID": "USER_MASTER_SEQ"}
    # Password may be sent to the target app table, but never persisted in the run record.
    persisted_text = repr(database.provisioning_runs.inserted) + repr(database.provisioning_runs.updates)
    assert "abc12345" not in persisted_text


@pytest.mark.asyncio
async def test_execute_provisioning_returns_partial_and_stops_after_failed_step(monkeypatch):
    database = FakeDatabase()
    profile = {
        "_id": ObjectId(PROFILE_ID),
        "name": "ORMS",
        "schema_connection_id": PARENT_ID,
        "ldap_enabled": False,
        "updated_at": datetime.now(timezone.utc),
        "table_steps": [
            {
                "name": "STEP 1",
                "connection_id": STEP_ID,
                "owner": "ORMS",
                "table_name": "ONE",
                "match_columns": ["USERNAME"],
                "mappings": [{"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"}],
            },
            {
                "name": "STEP 2",
                "connection_id": STEP_ID,
                "owner": "ORMS",
                "table_name": "TWO",
                "match_columns": ["USERNAME"],
                "mappings": [{"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"}],
            },
        ],
    }

    async def fake_preview(*_args, **_kwargs):
        value = preview()
        value.ldap = ProvisioningPreviewLdap(enabled=False)
        return value

    async def fake_profile(_database, _profile_id): return profile
    async def fake_connection(_database, connection_id): return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}
    async def fake_reference(_connection, _username): return {"username": "APP_USER", "roles": [{"name": "APP_READ", "sensitive": False}]}
    async def fake_reconcile(*_args, **_kwargs): return {"account_action": "altered", "password_applied": True, "roles_added": [], "roles_already_present": ["APP_READ"], "default_tablespace": None, "temporary_tablespace": None, "profile": None}
    calls = 0
    async def fake_upsert(_connection, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise AppError("application insert failed", code="TEST", status_code=400)
        raise AssertionError("Later steps must not run after a failure")
    async def fake_start(*_args, **_kwargs): return "audit-1"
    async def fake_finish(*_args, **_kwargs): return None

    monkeypatch.setattr(provisioning_execution, "build_provisioning_preview", fake_preview)
    monkeypatch.setattr(provisioning_execution, "get_provisioning_profile", fake_profile)
    monkeypatch.setattr(provisioning_execution, "get_database_connection", fake_connection)
    monkeypatch.setattr(provisioning_execution, "get_oracle_reference_user", fake_reference)
    monkeypatch.setattr(provisioning_execution, "reconcile_oracle_user", fake_reconcile)
    monkeypatch.setattr(provisioning_execution, "upsert_oracle_provisioning_row", fake_upsert)
    monkeypatch.setattr(provisioning_execution, "start_database_action", fake_start)
    monkeypatch.setattr(provisioning_execution, "finish_database_action", fake_finish)

    result = await provisioning_execution.execute_provisioning_profile(
        database, PARENT_ID, PROFILE_ID, execute_request(), operator()
    )

    assert result.status == "partial"
    assert result.table_steps[0].action == "failed"
    assert result.table_steps[1].action == "not_run"
    assert calls == 1
