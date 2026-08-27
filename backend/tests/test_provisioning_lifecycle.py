from datetime import datetime, timezone

import pytest
from bson import ObjectId

from app.schemas.provisioning import ProvisioningRetryRequest
from app.schemas.user import UserResponse, UserRole
from app.services import provisioning_lifecycle


PARENT_ID = "b" * 24
STEP_ID = "c" * 24
RUN_ID = ObjectId()


def operator():
    return UserResponse(
        id="admin-1",
        username="meimei",
        display_name="DBA",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )


def base_document():
    now = datetime.now(timezone.utc)
    return {
        "_id": RUN_ID,
        "parent_connection_id": PARENT_ID,
        "parent_connection_name": "RMSUAT SYS",
        "username": "JSMITH1001",
        "employee_id": "1001",
        "profile_id": "a" * 24,
        "profile_name": "ORMS",
        "status": "partial",
        "operator_username": "original-dba",
        "requester_ip": "192.0.2.1",
        "request_reference": "REQ-123",
        "requestor": "Requestor",
        "remarks": "Access",
        "reference_user": None,
        "account_existed_before": False,
        "account_settings": {
            "default_tablespace": "USERS",
            "temporary_tablespace": "TEMP",
            "oracle_profile": "DEFAULT",
        },
        "input_snapshot": {
            "username": "JSMITH1001",
            "first_name": "John",
            "middle_name": None,
            "last_name": "Smith",
            "employee_id": "1001",
            "reference_user": None,
            "requestor": "Requestor",
            "request_reference": "REQ-123",
            "remarks": "Access",
        },
        "generated_context": {
            "username": "JSMITH1001",
            "operator_username": "original-dba",
            "requester_ip": "192.0.2.1",
            "current_datetime": now,
        },
        "desired_roles": [],
        "profile_snapshot": {
            "name": "ORMS",
            "schema_connection_id": PARENT_ID,
            "ldap_enabled": False,
            "ldap_profile_id": None,
            "table_steps": [],
            "updated_at": now,
        },
        "ldap_snapshot": None,
        "retry_attempts": [],
        "retry_count": 0,
        "account": {
            "action": "created",
            "password_applied": True,
            "default_tablespace": "USERS",
            "temporary_tablespace": "TEMP",
            "oracle_profile": "DEFAULT",
            "error": None,
        },
        "roles": [],
        "table_steps": [],
        "ldap": {"enabled": False, "action": None},
        "error": "table failed",
        "started_at": now,
        "updated_at": now,
        "completed_at": now,
    }


class FakeRuns:
    def __init__(self, document):
        self.document = document
        self.updates = []

    async def find_one(self, query):
        if query.get("_id") == self.document["_id"] and query.get("parent_connection_id") == self.document["parent_connection_id"]:
            return self.document
        return None

    async def update_one(self, query, update):
        self.updates.append((query, update))
        for key, value in update.get("$set", {}).items():
            self.document[key] = value
        for key, value in update.get("$inc", {}).items():
            self.document[key] = self.document.get(key, 0) + value
        for key, value in update.get("$push", {}).items():
            self.document.setdefault(key, []).append(value)


class FakeDatabase:
    def __init__(self, document):
        self.provisioning_runs = FakeRuns(document)


@pytest.mark.asyncio
async def test_retry_requirement_only_requests_password_for_pending_password_step():
    document = base_document()
    document["profile_snapshot"]["table_steps"] = [
        {
            "name": "USER_MASTER",
            "connection_id": STEP_ID,
            "owner": "ORMS",
            "table_name": "USER_MASTER",
            "match_columns": ["USERNAME"],
            "mappings": [
                {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
                {"column_name": "PASSWORD", "value_kind": "generated", "value_key": "password"},
            ],
        }
    ]
    document["table_steps"] = [{
        "index": 1,
        "name": "USER_MASTER",
        "connection_id": STEP_ID,
        "connection_name": "ORMS APP",
        "owner": "ORMS",
        "table_name": "USER_MASTER",
        "action": "not_run",
    }]

    requirement = await provisioning_lifecycle.get_retry_requirement(
        FakeDatabase(document), PARENT_ID, str(RUN_ID)
    )

    assert requirement.retryable is True
    assert requirement.password_required is True
    assert requirement.pending == ["Table step 1: USER_MASTER"]


@pytest.mark.asyncio
async def test_retry_skips_completed_step_and_executes_only_incomplete_step(monkeypatch):
    document = base_document()
    document["profile_snapshot"]["table_steps"] = [
        {
            "name": "DONE",
            "connection_id": STEP_ID,
            "owner": "ORMS",
            "table_name": "DONE_TABLE",
            "match_columns": ["USERNAME"],
            "mappings": [
                {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
            ],
        },
        {
            "name": "PENDING",
            "connection_id": STEP_ID,
            "owner": "ORMS",
            "table_name": "PENDING_TABLE",
            "match_columns": ["USERNAME"],
            "mappings": [
                {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
                {"column_name": "REMARKS", "value_kind": "form", "value_key": "remarks"},
            ],
        },
    ]
    document["table_steps"] = [
        {
            "index": 1,
            "name": "DONE",
            "connection_id": STEP_ID,
            "connection_name": "ORMS APP",
            "owner": "ORMS",
            "table_name": "DONE_TABLE",
            "action": "inserted",
            "match_values": {"USERNAME": "JSMITH1001"},
            "after_values": {"USERNAME": "JSMITH1001"},
        },
        {
            "index": 2,
            "name": "PENDING",
            "connection_id": STEP_ID,
            "connection_name": "ORMS APP",
            "owner": "ORMS",
            "table_name": "PENDING_TABLE",
            "action": "failed",
            "match_values": {"USERNAME": "JSMITH1001"},
            "error": "network error",
        },
    ]
    database = FakeDatabase(document)
    upserts = []

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "RMSUAT SYS" if connection_id == PARENT_ID else "ORMS APP", "engine": "oracle", "active": True}

    async def fake_upsert(_connection, **kwargs):
        upserts.append(kwargs)
        return {
            "action": "inserted",
            "existing_rows": 0,
            "rowcount": 1,
            "generated_values": {},
            "before_values": {},
            "after_values": {"USERNAME": "JSMITH1001", "REMARKS": "Access"},
        }

    async def fake_start(*_args, **_kwargs):
        return "audit-1"

    async def fake_finish(*_args, **_kwargs):
        return None

    monkeypatch.setattr(provisioning_lifecycle, "get_database_connection", fake_connection)
    monkeypatch.setattr(provisioning_lifecycle, "upsert_oracle_provisioning_row", fake_upsert)
    monkeypatch.setattr(provisioning_lifecycle, "start_database_action", fake_start)
    monkeypatch.setattr(provisioning_lifecycle, "finish_database_action", fake_finish)

    result = await provisioning_lifecycle.retry_provisioning_run(
        database,
        PARENT_ID,
        str(RUN_ID),
        ProvisioningRetryRequest(password=None),
        operator(),
        requester_ip="192.0.2.25",
    )

    assert result.status == "succeeded"
    assert len(upserts) == 1
    assert upserts[0]["table_name"] == "PENDING_TABLE"
    assert result.table_steps[0].action == "inserted"  # original successful step preserved
    assert result.table_steps[1].action == "inserted"
    assert database.provisioning_runs.document["retry_count"] == 1


@pytest.mark.asyncio
async def test_retry_password_is_used_but_never_persisted(monkeypatch):
    document = base_document()
    document["profile_snapshot"]["table_steps"] = [{
        "name": "USER_MASTER",
        "connection_id": STEP_ID,
        "owner": "ORMS",
        "table_name": "USER_MASTER",
        "match_columns": ["USERNAME"],
        "mappings": [
            {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
            {"column_name": "PASSWORD", "value_kind": "generated", "value_key": "password"},
        ],
    }]
    document["table_steps"] = [{
        "index": 1,
        "name": "USER_MASTER",
        "connection_id": STEP_ID,
        "connection_name": "ORMS APP",
        "owner": "ORMS",
        "table_name": "USER_MASTER",
        "action": "failed",
        "error": "temporary failure",
    }]
    database = FakeDatabase(document)
    captured = {}

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "ORMS APP", "engine": "oracle", "active": True}

    async def fake_upsert(_connection, **kwargs):
        captured.update(kwargs)
        return {
            "action": "inserted",
            "existing_rows": 0,
            "rowcount": 1,
            "generated_values": {},
            "before_values": {},
            "after_values": {"USERNAME": "JSMITH1001", "PASSWORD": "abc12345"},
        }

    async def fake_start(*_args, **_kwargs):
        return "audit-1"

    async def fake_finish(*_args, **_kwargs):
        return None

    monkeypatch.setattr(provisioning_lifecycle, "get_database_connection", fake_connection)
    monkeypatch.setattr(provisioning_lifecycle, "upsert_oracle_provisioning_row", fake_upsert)
    monkeypatch.setattr(provisioning_lifecycle, "start_database_action", fake_start)
    monkeypatch.setattr(provisioning_lifecycle, "finish_database_action", fake_finish)

    result = await provisioning_lifecycle.retry_provisioning_run(
        database,
        PARENT_ID,
        str(RUN_ID),
        ProvisioningRetryRequest(password="abc12345"),
        operator(),
    )

    assert captured["insert_values"]["PASSWORD"] == "abc12345"
    assert result.table_steps[0].after_values["PASSWORD"] == "<redacted>"
    assert "abc12345" not in repr(database.provisioning_runs.updates)
    assert "abc12345" not in repr(database.provisioning_runs.document)


@pytest.mark.asyncio
async def test_deprovision_preview_blocks_sensitive_insert_even_when_lifecycle_created_it(monkeypatch):
    document = base_document()
    document["profile_snapshot"]["table_steps"] = [{
        "name": "USER_MASTER",
        "connection_id": STEP_ID,
        "owner": "ORMS",
        "table_name": "USER_MASTER",
        "match_columns": ["USERNAME"],
        "mappings": [
            {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
            {"column_name": "PASSWORD", "value_kind": "generated", "value_key": "password"},
        ],
    }]
    document["table_steps"] = [{
        "index": 1,
        "name": "USER_MASTER",
        "connection_id": STEP_ID,
        "connection_name": "ORMS APP",
        "owner": "ORMS",
        "table_name": "USER_MASTER",
        "action": "inserted",
        "match_values": {"USERNAME": "JSMITH1001"},
        "after_values": {"USERNAME": "JSMITH1001", "PASSWORD": "<redacted>"},
        "sensitive_columns": ["PASSWORD"],
    }]
    database = FakeDatabase(document)

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}

    async def fake_user_exists(_connection, _username):
        return True

    async def should_not_fetch(*_args, **_kwargs):
        raise AssertionError("Sensitive rows must be blocked before live row fetch")

    monkeypatch.setattr(provisioning_lifecycle, "get_database_connection", fake_connection)
    monkeypatch.setattr(provisioning_lifecycle, "oracle_user_exists", fake_user_exists)
    monkeypatch.setattr(provisioning_lifecycle, "fetch_oracle_provisioning_row", should_not_fetch)

    preview = await provisioning_lifecycle.build_deprovision_preview(
        database, PARENT_ID, str(RUN_ID)
    )

    table_item = next(item for item in preview.items if item.component == "table")
    assert table_item.state == "blocked"
    assert table_item.safe_to_reverse is False
    assert preview.destructive_execution_enabled is False


@pytest.mark.asyncio
async def test_deprovision_preview_marks_matching_non_sensitive_insert_as_safe_candidate(monkeypatch):
    document = base_document()
    document["account"]["action"] = "altered"
    document["account_existed_before"] = True
    document["profile_snapshot"]["table_steps"] = [{
        "name": "AUDIT_ROW",
        "connection_id": STEP_ID,
        "owner": "ORMS",
        "table_name": "USER_AUDIT",
        "match_columns": ["USERNAME"],
        "mappings": [
            {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
            {"column_name": "REMARKS", "value_kind": "form", "value_key": "remarks"},
        ],
    }]
    document["table_steps"] = [{
        "index": 1,
        "name": "AUDIT_ROW",
        "connection_id": STEP_ID,
        "connection_name": "ORMS APP",
        "owner": "ORMS",
        "table_name": "USER_AUDIT",
        "action": "inserted",
        "match_values": {"USERNAME": "JSMITH1001"},
        "after_values": {"USERNAME": "JSMITH1001", "REMARKS": "Access"},
        "sensitive_columns": [],
    }]
    database = FakeDatabase(document)

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}

    async def fake_fetch(*_args, **_kwargs):
        return {
            "existing_rows": 1,
            "values": {"USERNAME": "JSMITH1001", "REMARKS": "Access"},
        }

    monkeypatch.setattr(provisioning_lifecycle, "get_database_connection", fake_connection)
    monkeypatch.setattr(provisioning_lifecycle, "fetch_oracle_provisioning_row", fake_fetch)

    preview = await provisioning_lifecycle.build_deprovision_preview(
        database, PARENT_ID, str(RUN_ID)
    )

    table_item = next(item for item in preview.items if item.component == "table")
    assert table_item.state == "candidate"
    assert table_item.safe_to_reverse is True
    assert preview.safe_candidate_count == 1


@pytest.mark.asyncio
async def test_deprovision_preview_blocks_row_changed_after_provisioning(monkeypatch):
    document = base_document()
    document["account"]["action"] = "altered"
    document["account_existed_before"] = True
    document["profile_snapshot"]["table_steps"] = [{
        "name": "USER_MASTER",
        "connection_id": STEP_ID,
        "owner": "ORMS",
        "table_name": "USER_MASTER",
        "match_columns": ["USERNAME"],
        "mappings": [
            {"column_name": "USERNAME", "value_kind": "generated", "value_key": "username"},
            {"column_name": "REMARKS", "value_kind": "form", "value_key": "remarks"},
        ],
    }]
    document["table_steps"] = [{
        "index": 1,
        "name": "USER_MASTER",
        "connection_id": STEP_ID,
        "connection_name": "ORMS APP",
        "owner": "ORMS",
        "table_name": "USER_MASTER",
        "action": "updated",
        "match_values": {"USERNAME": "JSMITH1001"},
        "before_values": {"USERNAME": "JSMITH1001", "REMARKS": "Old"},
        "after_values": {"USERNAME": "JSMITH1001", "REMARKS": "Access"},
        "sensitive_columns": [],
    }]
    database = FakeDatabase(document)

    async def fake_connection(_database, connection_id):
        return {"_id": connection_id, "name": "Oracle", "engine": "oracle", "active": True}

    async def fake_fetch(*_args, **_kwargs):
        return {
            "existing_rows": 1,
            "values": {"USERNAME": "JSMITH1001", "REMARKS": "Changed later"},
        }

    monkeypatch.setattr(provisioning_lifecycle, "get_database_connection", fake_connection)
    monkeypatch.setattr(provisioning_lifecycle, "fetch_oracle_provisioning_row", fake_fetch)

    preview = await provisioning_lifecycle.build_deprovision_preview(
        database, PARENT_ID, str(RUN_ID)
    )

    table_item = next(item for item in preview.items if item.component == "table")
    assert table_item.state == "blocked"
    assert "no longer exactly matches" in table_item.reason
