from datetime import datetime, timezone

import pytest

from app.schemas.provisioning import (
    OracleUserDeprovisionPreviewItem,
    OracleUserDeprovisionPreviewResponse,
    OracleUserDeprovisionRequest,
)
from app.schemas.user import UserResponse, UserRole
from app.services import deprovisioning


PARENT_ID = "b" * 24
STEP_ID = "c" * 24


class EmptyCursor:
    def sort(self, *_args, **_kwargs):
        return self

    async def to_list(self, _limit):
        return []


class EmptyRuns:
    def find(self, _query):
        return EmptyCursor()


class FakeDatabase:
    def __init__(self):
        self.provisioning_runs = EmptyRuns()


def operator():
    return UserResponse(
        id="admin-1",
        username="meimei",
        display_name="DBA",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_generic_preview_does_not_require_dbachum_lifecycle(monkeypatch):
    database = FakeDatabase()

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}

    async def fake_state(_connection, username):
        assert username == "LEGACY01"
        return {"exists": True, "account_status": "OPEN", "owned_object_count": 7}

    async def fake_profiles(_database, connection_id):
        assert connection_id == PARENT_ID
        return [{
            "id": "a" * 24,
            "name": "OREIM",
            "schema_connection_id": PARENT_ID,
            "enabled": True,
            "table_steps": [{
                "name": "USER_MASTER",
                "connection_id": STEP_ID,
                "owner": "OREIM",
                "table_name": "USER_MASTER",
                "match_columns": ["USERNAME"],
                "mappings": [
                    {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
                    {"column_name": "REMARKS", "value_kind": "custom", "custom_value": "DBAChum"},
                ],
            }],
        }]

    async def fake_count(_connection, **kwargs):
        assert kwargs["match_values"] == {"USERNAME": "LEGACY01"}
        return 1

    monkeypatch.setattr(deprovisioning, "get_database_connection", fake_connection)
    monkeypatch.setattr(deprovisioning, "get_oracle_user_deprovision_state", fake_state)
    monkeypatch.setattr(deprovisioning, "list_provisioning_profiles_for_connection", fake_profiles)
    monkeypatch.setattr(deprovisioning, "count_oracle_rows_by_match", fake_count)

    preview = await deprovisioning.build_oracle_user_deprovision_preview(
        database, PARENT_ID, "legacy01"
    )

    assert preview.lifecycle_run_count == 0
    assert preview.account_exists is True
    assert preview.owned_object_count == 7
    assert preview.drop_cascade is True
    assert preview.linked_row_count == 1
    assert preview.execution_ready is True
    table = next(item for item in preview.items if item.component == "table")
    assert table.state == "candidate"
    assert table.match_values == {"USERNAME": "LEGACY01"}


@pytest.mark.asyncio
async def test_preview_blocks_ambiguous_linked_table_rows(monkeypatch):
    database = FakeDatabase()

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}

    async def fake_state(_connection, _username):
        return {"exists": True, "account_status": "OPEN", "owned_object_count": 0}

    async def fake_profiles(_database, _connection_id):
        return [{
            "id": "a" * 24,
            "name": "OREIM",
            "table_steps": [{
                "name": "USER_MASTER",
                "connection_id": STEP_ID,
                "owner": "OREIM",
                "table_name": "USER_MASTER",
                "match_columns": ["USERNAME"],
                "mappings": [
                    {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
                ],
            }],
        }]

    async def fake_count(*_args, **_kwargs):
        return 2

    monkeypatch.setattr(deprovisioning, "get_database_connection", fake_connection)
    monkeypatch.setattr(deprovisioning, "get_oracle_user_deprovision_state", fake_state)
    monkeypatch.setattr(deprovisioning, "list_provisioning_profiles_for_connection", fake_profiles)
    monkeypatch.setattr(deprovisioning, "count_oracle_rows_by_match", fake_count)

    preview = await deprovisioning.build_oracle_user_deprovision_preview(
        database, PARENT_ID, "LEGACY01"
    )

    assert preview.execution_ready is False
    assert preview.blocked_count == 1
    assert any("matches 2 rows" in reason for reason in preview.blocked_reasons)


@pytest.mark.asyncio
async def test_execute_requires_exact_schema_confirmation(monkeypatch):
    with pytest.raises(Exception) as exc_info:
        await deprovisioning.execute_oracle_user_deprovision(
            FakeDatabase(),
            PARENT_ID,
            "LEGACY01",
            OracleUserDeprovisionRequest(confirmation="legacy01"),
            operator(),
        )
    assert "exact schema name" in str(exc_info.value)


@pytest.mark.asyncio
async def test_execute_deletes_linked_row_then_drops_schema(monkeypatch):
    database = FakeDatabase()
    preview = OracleUserDeprovisionPreviewResponse(
        username="LEGACY01",
        generated_at=datetime.now(timezone.utc),
        account_exists=True,
        account_status="OPEN",
        protected_account=False,
        owned_object_count=3,
        drop_cascade=True,
        lifecycle_run_count=0,
        linked_row_count=1,
        blocked_count=0,
        execution_ready=True,
        confirmation_text="LEGACY01",
        items=[
            OracleUserDeprovisionPreviewItem(
                component="table",
                label="OREIM · Step 1 · OREIM.USER_MASTER",
                planned_action="DELETE linked provisioning row",
                state="candidate",
                reason="one row",
                profile_id="a" * 24,
                profile_name="OREIM",
                step_index=1,
                connection_id=STEP_ID,
                owner="OREIM",
                table_name="USER_MASTER",
                match_values={"USERNAME": "LEGACY01"},
                existing_rows=1,
            ),
            OracleUserDeprovisionPreviewItem(
                component="account",
                label="Oracle schema LEGACY01",
                planned_action="DROP USER LEGACY01 CASCADE",
                state="candidate",
                reason="3 objects",
            ),
        ],
    )
    calls = []

    async def fake_preview(*_args, **_kwargs):
        return preview

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}

    async def fake_start(*_args, **_kwargs):
        return "audit-1"

    async def fake_finish(*_args, **_kwargs):
        calls.append(("audit", _kwargs.get("status")))
        return None

    async def fake_delete(_connection, **kwargs):
        calls.append(("delete", kwargs["table_name"], kwargs["match_values"]))
        return 1

    async def fake_drop(_connection, username, *, cascade):
        calls.append(("drop", username, cascade))

    monkeypatch.setattr(deprovisioning, "build_oracle_user_deprovision_preview", fake_preview)
    monkeypatch.setattr(deprovisioning, "get_database_connection", fake_connection)
    monkeypatch.setattr(deprovisioning, "start_database_action", fake_start)
    monkeypatch.setattr(deprovisioning, "finish_database_action", fake_finish)
    monkeypatch.setattr(deprovisioning, "delete_oracle_provisioning_row", fake_delete)
    monkeypatch.setattr(deprovisioning, "drop_oracle_user", fake_drop)

    result = await deprovisioning.execute_oracle_user_deprovision(
        database,
        PARENT_ID,
        "LEGACY01",
        OracleUserDeprovisionRequest(confirmation="LEGACY01"),
        operator(),
    )

    assert result.status == "succeeded"
    assert result.account_dropped is True
    assert result.deleted_provisioning_rows == 1
    assert calls[0][0] == "delete"
    assert calls[1] == ("drop", "LEGACY01", True)


@pytest.mark.asyncio
async def test_preview_omits_ldap_when_profile_does_not_enable_it(monkeypatch):
    database = FakeDatabase()

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}

    async def fake_state(_connection, _username):
        return {"exists": True, "account_status": "OPEN", "owned_object_count": 0}

    async def fake_profiles(_database, _connection_id):
        return [{
            "id": "a" * 24,
            "name": "No LDAP",
            "enabled": True,
            "ldap_enabled": False,
            "table_steps": [],
        }]

    async def should_not_lookup(*_args, **_kwargs):
        raise AssertionError("LDAP must not be inspected when the provisioning profile disables it")

    monkeypatch.setattr(deprovisioning, "get_database_connection", fake_connection)
    monkeypatch.setattr(deprovisioning, "get_oracle_user_deprovision_state", fake_state)
    monkeypatch.setattr(deprovisioning, "list_provisioning_profiles_for_connection", fake_profiles)
    monkeypatch.setattr(deprovisioning, "find_ldap_entries_for_username", should_not_lookup)

    preview = await deprovisioning.build_oracle_user_deprovision_preview(
        database, PARENT_ID, "LEGACY01"
    )

    assert preview.linked_ldap_count == 0
    assert not any(item.component == "ldap" for item in preview.items)
    assert not any("ldap" in warning.lower() for warning in preview.warnings)


@pytest.mark.asyncio
async def test_preview_includes_one_unambiguous_ldap_entry_when_enabled(monkeypatch):
    database = FakeDatabase()

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}

    async def fake_state(_connection, _username):
        return {"exists": True, "account_status": "OPEN", "owned_object_count": 0}

    async def fake_profiles(_database, _connection_id):
        return [{
            "id": "a" * 24,
            "name": "OREIM",
            "enabled": True,
            "ldap_enabled": True,
            "ldap_profile_id": "global",
            "table_steps": [],
        }]

    async def fake_ldap_profile(_database, profile_id):
        assert profile_id == "global"
        return {"_id": "global", "name": "LDAP", "enabled": True}

    async def fake_lookup(_profile, username):
        assert username == "LEGACY01"
        return ["cn=LEGACY01,cn=Users,dc=example,dc=com"]

    monkeypatch.setattr(deprovisioning, "get_database_connection", fake_connection)
    monkeypatch.setattr(deprovisioning, "get_oracle_user_deprovision_state", fake_state)
    monkeypatch.setattr(deprovisioning, "list_provisioning_profiles_for_connection", fake_profiles)
    monkeypatch.setattr(deprovisioning, "get_ldap_profile_document", fake_ldap_profile)
    monkeypatch.setattr(deprovisioning, "find_ldap_entries_for_username", fake_lookup)

    preview = await deprovisioning.build_oracle_user_deprovision_preview(
        database, PARENT_ID, "LEGACY01"
    )

    ldap = next(item for item in preview.items if item.component == "ldap")
    assert ldap.state == "candidate"
    assert ldap.ldap_profile_id == "global"
    assert ldap.ldap_dn == "cn=LEGACY01,cn=Users,dc=example,dc=com"
    assert preview.linked_ldap_count == 1
    assert preview.execution_ready is True


@pytest.mark.asyncio
async def test_execute_deletes_ldap_before_dropping_schema(monkeypatch):
    database = FakeDatabase()
    preview = OracleUserDeprovisionPreviewResponse(
        username="LEGACY01",
        generated_at=datetime.now(timezone.utc),
        account_exists=True,
        account_status="OPEN",
        protected_account=False,
        owned_object_count=0,
        drop_cascade=False,
        lifecycle_run_count=0,
        linked_row_count=0,
        linked_ldap_count=1,
        blocked_count=0,
        execution_ready=True,
        confirmation_text="LEGACY01",
        items=[
            OracleUserDeprovisionPreviewItem(
                component="ldap",
                label="OREIM · LDAP entry",
                planned_action="DELETE LDAP entry",
                state="candidate",
                reason="one entry",
                profile_id="a" * 24,
                profile_name="OREIM",
                ldap_profile_id="global",
                ldap_dn="cn=LEGACY01,cn=Users,dc=example,dc=com",
            ),
            OracleUserDeprovisionPreviewItem(
                component="account",
                label="Oracle schema LEGACY01",
                planned_action="DROP USER LEGACY01",
                state="candidate",
                reason="no objects",
            ),
        ],
    )
    calls = []

    async def fake_preview(*_args, **_kwargs): return preview
    async def fake_connection(_database, connection_id): return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}
    async def fake_start(*_args, **_kwargs): return "audit-1"
    async def fake_finish(*_args, **_kwargs): return None
    async def fake_ldap_profile(_database, profile_id):
        assert profile_id == "global"
        return {"enabled": True}
    async def fake_ldap_delete(_profile, dn):
        calls.append(("ldap", dn))
        return True
    async def fake_drop(_connection, username, *, cascade):
        calls.append(("drop", username, cascade))

    monkeypatch.setattr(deprovisioning, "build_oracle_user_deprovision_preview", fake_preview)
    monkeypatch.setattr(deprovisioning, "get_database_connection", fake_connection)
    monkeypatch.setattr(deprovisioning, "start_database_action", fake_start)
    monkeypatch.setattr(deprovisioning, "finish_database_action", fake_finish)
    monkeypatch.setattr(deprovisioning, "get_ldap_profile_document", fake_ldap_profile)
    monkeypatch.setattr(deprovisioning, "delete_ldap_entry", fake_ldap_delete)
    monkeypatch.setattr(deprovisioning, "drop_oracle_user", fake_drop)

    result = await deprovisioning.execute_oracle_user_deprovision(
        database, PARENT_ID, "LEGACY01",
        OracleUserDeprovisionRequest(confirmation="LEGACY01"), operator(),
    )

    assert result.status == "succeeded"
    assert result.deleted_ldap_entries == 1
    assert calls == [
        ("ldap", "cn=LEGACY01,cn=Users,dc=example,dc=com"),
        ("drop", "LEGACY01", False),
    ]
