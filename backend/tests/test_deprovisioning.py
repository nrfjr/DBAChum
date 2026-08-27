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
