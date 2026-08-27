from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId

from app.core.exceptions import AppError
from app.schemas.oracle_dba import (
    OracleUserAccountActionRequest,
    OracleUserEditExecuteRequest,
    OracleUserEditRequest,
    OracleUserPasswordResetRequest,
)
from app.schemas.user import UserResponse, UserRole
from app.services import oracle_user_lifecycle as lifecycle


class FakeAuditCollection:
    def __init__(self):
        self.documents = {}

    async def insert_one(self, document):
        object_id = ObjectId()
        self.documents[object_id] = {**document, "_id": object_id}
        return SimpleNamespace(inserted_id=object_id)

    async def update_one(self, query, update):
        document = self.documents.get(query["_id"])
        if document is None or document.get("status") != query.get("status"):
            return SimpleNamespace(matched_count=0)
        document.update(update["$set"])
        return SimpleNamespace(matched_count=1)

    async def find_one(self, query):
        return self.documents.get(query["_id"])


class FakeDatabase:
    def __init__(self):
        self.database_action_audit = FakeAuditCollection()


def operator():
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


def state(*, locked=False, expired=False, roles=None):
    return {
        "username": "APPUSER",
        "status": "LOCKED" if locked else ("EXPIRED" if expired else "OPEN"),
        "locked": locked,
        "expired": expired,
        "default_tablespace": "USERS",
        "temporary_tablespace": "TEMP",
        "profile": "DEFAULT",
        "created_at": None,
        "lock_date": None,
        "expiry_date": None,
        "roles": [
            {"name": name, "admin_option": False, "default_role": True, "sensitive": name == "DBA"}
            for name in (roles or ["CONNECT"])
        ],
        "system_privileges": [],
        "available_roles": [
            {"name": "CONNECT", "sensitive": False},
            {"name": "RESOURCE", "sensitive": False},
            {"name": "DBA", "sensitive": True},
        ],
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_edit_preview_shows_role_and_lock_changes(monkeypatch):
    monkeypatch.setattr(lifecycle, "get_oracle_target", lambda *_args: None)

    async def fake_target(*_args):
        return {"engine": "oracle"}

    async def fake_state(*_args):
        return state()

    monkeypatch.setattr(lifecycle, "get_oracle_target", fake_target)
    monkeypatch.setattr(lifecycle, "get_oracle_user_lifecycle_state", fake_state)

    result = await lifecycle.build_oracle_user_edit_preview(
        FakeDatabase(),
        "conn-1",
        "APPUSER",
        OracleUserEditRequest(
            roles=["RESOURCE"],
            default_tablespace="USERS",
            temporary_tablespace="TEMP",
            profile="DEFAULT",
            locked=True,
        ),
    )

    changes = {(item.action, item.label) for item in result.changes}
    assert ("grant", "RESOURCE") in changes
    assert ("revoke", "CONNECT") in changes
    assert ("lock", "Account state") in changes
    assert result.ready_to_execute is True


@pytest.mark.asyncio
async def test_edit_preview_blocks_new_sensitive_role(monkeypatch):
    async def fake_target(*_args):
        return {"engine": "oracle"}

    async def fake_state(*_args):
        return state()

    monkeypatch.setattr(lifecycle, "get_oracle_target", fake_target)
    monkeypatch.setattr(lifecycle, "get_oracle_user_lifecycle_state", fake_state)

    with pytest.raises(AppError) as exc:
        await lifecycle.build_oracle_user_edit_preview(
            FakeDatabase(),
            "conn-1",
            "APPUSER",
            OracleUserEditRequest(
                roles=["CONNECT", "DBA"],
                default_tablespace="USERS",
                temporary_tablespace="TEMP",
                profile="DEFAULT",
                locked=False,
            ),
        )

    assert exc.value.code == "ORACLE_SENSITIVE_ROLE_ADD_BLOCKED"


@pytest.mark.asyncio
async def test_password_reset_audit_never_persists_password(monkeypatch):
    database = FakeDatabase()
    calls = {"count": 0}

    async def fake_target(*_args):
        return {"engine": "oracle"}

    async def fake_state(*_args):
        calls["count"] += 1
        return state(expired=calls["count"] > 1)

    async def fake_reset(_connection, **kwargs):
        assert kwargs["password"] == "secret123"
        assert kwargs["expire_after_reset"] is True

    monkeypatch.setattr(lifecycle, "get_oracle_target", fake_target)
    monkeypatch.setattr(lifecycle, "get_oracle_user_lifecycle_state", fake_state)
    monkeypatch.setattr(lifecycle, "reset_oracle_user_password", fake_reset)

    result = await lifecycle.execute_oracle_user_password_reset(
        database,
        "conn-1",
        "APPUSER",
        OracleUserPasswordResetRequest(
            password="secret123",
            expire_after_reset=True,
            request_reference="REQ-9",
        ),
        operator(),
    )

    assert result.status == "succeeded"
    audit = next(iter(database.database_action_audit.documents.values()))
    serialized = repr(audit)
    assert "secret123" not in serialized
    assert audit["details"]["password_persisted"] is False
    assert audit["details"]["expire_after_reset"] is True


@pytest.mark.asyncio
async def test_account_lock_action_is_audited(monkeypatch):
    database = FakeDatabase()
    calls = {"count": 0}

    async def fake_target(*_args):
        return {"engine": "oracle"}

    async def fake_state(*_args):
        calls["count"] += 1
        return state(locked=calls["count"] > 1)

    async def fake_action(_connection, **kwargs):
        assert kwargs == {"username": "APPUSER", "action": "lock"}

    monkeypatch.setattr(lifecycle, "get_oracle_target", fake_target)
    monkeypatch.setattr(lifecycle, "get_oracle_user_lifecycle_state", fake_state)
    monkeypatch.setattr(lifecycle, "execute_oracle_user_account_action", fake_action)

    result = await lifecycle.execute_oracle_user_lifecycle_action(
        database,
        "conn-1",
        "APPUSER",
        OracleUserAccountActionRequest(action="lock", request_reference="REQ-10"),
        operator(),
    )

    assert result.status == "succeeded"
    assert result.after.locked is True
    audit = next(iter(database.database_action_audit.documents.values()))
    assert audit["action"] == "user_lock"
    assert audit["request_reference"] == "REQ-10"
