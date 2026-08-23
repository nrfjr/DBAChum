from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId

from app.schemas.database_action import (
    DatabaseActionRisk,
    DatabaseActionStatus,
)
from app.schemas.user import UserResponse, UserRole
from app.services import database_actions


class FakeAuditCursor:
    def __init__(self, documents):
        self.documents = documents

    def sort(self, *_args):
        return self

    async def to_list(self, length):
        return list(self.documents[:length])


class FakeAuditCollection:
    def __init__(self):
        self.documents = {}
        self.last_find_query = None

    async def insert_one(self, document):
        object_id = ObjectId()
        stored = dict(document)
        stored["_id"] = object_id
        self.documents[object_id] = stored
        return SimpleNamespace(inserted_id=object_id)

    async def update_one(self, query, update):
        document = self.documents.get(query["_id"])

        if (
            document is None
            or document.get("status") != query.get("status")
        ):
            return SimpleNamespace(matched_count=0)

        document.update(update["$set"])
        return SimpleNamespace(matched_count=1)

    async def find_one(self, query):
        return self.documents.get(query["_id"])

    def find(self, query):
        self.last_find_query = query
        documents = [
            document
            for document in self.documents.values()
            if document["connection_id"]
            == query["connection_id"]
        ]
        documents.sort(
            key=lambda item: item["started_at"],
            reverse=True,
        )
        return FakeAuditCursor(documents)


class FakeDatabase:
    def __init__(self):
        self.database_action_audit = FakeAuditCollection()


def make_operator():
    return UserResponse(
        id="operator-1",
        username="dba01",
        display_name="DBA 01",
        role=UserRole.OPERATOR,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_database_action_audit_tracks_start_and_finish():
    database = FakeDatabase()

    audit_id = await database_actions.start_database_action(
        database,
        connection_id="conn-1",
        engine="oracle",
        action="create_user",
        target="NEWUSER",
        operator=make_operator(),
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference="REQ-123",
        before={"exists": False},
    )

    response = await database_actions.finish_database_action(
        database,
        audit_id,
        status=DatabaseActionStatus.SUCCEEDED,
        after={"exists": True},
        details={"roles_applied": 3},
    )

    assert response.connection_id == "conn-1"
    assert response.action == "create_user"
    assert response.target == "NEWUSER"
    assert response.status == DatabaseActionStatus.SUCCEEDED
    assert response.operator_username == "dba01"
    assert response.request_reference == "REQ-123"
    assert response.before == {"exists": False}
    assert response.after == {"exists": True}
    assert response.details == {"roles_applied": 3}
    assert response.completed_at is not None


@pytest.mark.asyncio
async def test_database_action_history_is_scoped_to_connection():
    database = FakeDatabase()
    operator = make_operator()

    for connection_id in ("conn-1", "conn-2"):
        await database_actions.start_database_action(
            database,
            connection_id=connection_id,
            engine="oracle",
            action="inspect_user",
            target="APPUSER",
            operator=operator,
            risk=DatabaseActionRisk.SAFE,
        )

    result = await database_actions.list_database_actions(
        database,
        "conn-1",
    )

    assert len(result) == 1
    assert result[0].connection_id == "conn-1"
    assert (
        database.database_action_audit.last_find_query
        == {"connection_id": "conn-1"}
    )
