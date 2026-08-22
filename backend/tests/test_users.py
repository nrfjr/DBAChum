from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError
from app.schemas.user import (
    UserCreate,
    UserRole,
    UserUpdate,
)
from app.services import users


class FakeUsersCollection:
    def __init__(self):
        self.documents = {}
        self.inserted_document = None
        self.updated_payload = None

    async def insert_one(self, document):
        self.inserted_document = dict(document)
        object_id = "created-user-id"
        stored = dict(document)
        stored["_id"] = object_id
        self.documents[object_id] = stored
        return SimpleNamespace(inserted_id=object_id)

    async def find_one(self, query):
        if "_id" in query:
            return self.documents.get(query["_id"])
        return None

    async def update_one(self, query, update):
        object_id = query["_id"]
        document = self.documents.get(object_id)
        if document is None:
            return SimpleNamespace(matched_count=0)
        document.update(update["$set"])
        self.updated_payload = dict(update["$set"])
        return SimpleNamespace(matched_count=1)


class FakeSessionsCollection:
    async def delete_many(self, _query):
        return None


class FakeDatabase:
    def __init__(self):
        self.users = FakeUsersCollection()
        self.auth_sessions = FakeSessionsCollection()


@pytest.mark.asyncio
async def test_created_username_is_normalized_for_login(
    monkeypatch,
):
    database = FakeDatabase()

    monkeypatch.setattr(
        users,
        "hash_password",
        lambda password: f"hashed:{password}",
    )

    result = await users.create_managed_user(
        database,
        UserCreate(
            username="  ReleaseAdmin  ",
            password="strong-password",
            role=UserRole.ADMIN,
            is_active=True,
        ),
    )

    assert result.username == "releaseadmin"
    assert (
        database.users.inserted_document["username"]
        == "releaseadmin"
    )
    assert (
        database.users.inserted_document["username_key"]
        == "releaseadmin"
    )


def test_user_update_accepts_frontend_is_active_contract():
    payload = UserUpdate(
        role=UserRole.OPERATOR,
        is_active=False,
    )

    assert payload.role == UserRole.OPERATOR
    assert payload.is_active is False


def test_user_update_rejects_legacy_enabled_field():
    with pytest.raises(Exception):
        UserUpdate(
            role=UserRole.VIEWER,
            enabled=False,
        )


def test_user_create_rejects_whitespace_only_username():
    with pytest.raises(Exception):
        UserCreate(
            username="   ",
            password="strong-password",
            role=UserRole.VIEWER,
            is_active=True,
        )


def test_managed_user_password_requires_twelve_characters():
    from pydantic import ValidationError

    from app.schemas.user import (
        UserCreate,
        UserPasswordUpdate,
    )

    with pytest.raises(ValidationError):
        UserCreate(
            username="operator",
            password="shortpass",
        )

    with pytest.raises(ValidationError):
        UserPasswordUpdate(
            password="shortpass",
        )

    created = UserCreate(
        username="operator",
        password="twelve-chars!",
    )
    reset = UserPasswordUpdate(
        password="another-pass!",
    )

    assert created.username == "operator"
    assert reset.password == "another-pass!"
