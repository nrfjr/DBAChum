from types import SimpleNamespace

import pytest
from bson import ObjectId

from app.schemas.user import (
    AccentPreference,
    ThemePreference,
    UserPreferencesUpdate,
    UserProfileUpdate,
)
from app.services import users


class FakeUsersCollection:
    def __init__(self, document):
        self.document = dict(document)

    async def find_one(self, query):
        if query.get("_id") == self.document.get("_id"):
            return dict(self.document)
        return None

    async def update_one(self, query, update):
        if query.get("_id") != self.document.get("_id"):
            return SimpleNamespace(matched_count=0)

        for key, value in update.get("$set", {}).items():
            if "." in key:
                first, second = key.split(".", 1)
                nested = self.document.setdefault(first, {})
                nested[second] = value
            else:
                self.document[key] = value

        for key in update.get("$unset", {}):
            self.document.pop(key, None)

        return SimpleNamespace(matched_count=1)


class FakeDatabase:
    def __init__(self, document):
        self.users = FakeUsersCollection(document)


def base_user():
    return {
        "_id": ObjectId(),
        "username": "nrfjr",
        "display_name": "Nurfajar Sali",
        "role": "admin",
        "is_active": True,
    }


def test_existing_user_gets_safe_profile_defaults():
    result = users.user_to_response(base_user())

    assert result.email is None
    assert result.avatar_initials == "NS"
    assert result.preferences.theme.value == "system"
    assert result.preferences.accent.value == "purple"
    assert result.preferences.timezone == "system"


@pytest.mark.asyncio
async def test_user_can_update_own_identity():
    document = base_user()
    database = FakeDatabase(document)

    result = await users.update_current_user_profile(
        database,
        str(document["_id"]),
        UserProfileUpdate(
            display_name="  Nur Fajar Sali  ",
            email="DBA@Example.COM",
        ),
    )

    assert result.display_name == "Nur Fajar Sali"
    assert str(result.email) == "dba@example.com"
    assert result.avatar_initials == "NS"
    assert database.users.document["email_key"] == "dba@example.com"


@pytest.mark.asyncio
async def test_preference_update_merges_without_erasing_other_values():
    document = base_user()
    document["preferences"] = {
        "timezone": "Asia/Manila",
        "theme": "system",
        "accent": "purple",
        "density": "comfortable",
    }
    database = FakeDatabase(document)

    result = await users.update_current_user_preferences(
        database,
        str(document["_id"]),
        UserPreferencesUpdate(
            theme=ThemePreference.DARK,
            accent=AccentPreference.CYAN,
        ),
    )

    assert result.preferences.theme == ThemePreference.DARK
    assert result.preferences.accent == AccentPreference.CYAN
    assert result.preferences.timezone == "Asia/Manila"
    assert result.preferences.density.value == "comfortable"
