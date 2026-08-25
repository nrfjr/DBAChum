from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.services.provisioning import (
    LEGACY_LDAP_PROFILE_ID,
    ensure_ldap_profiles_migrated,
)


class MemoryCollection:
    def __init__(self, documents=None):
        self.documents = {doc["_id"]: deepcopy(doc) for doc in (documents or [])}

    async def find_one(self, query):
        if "_id" in query and not isinstance(query["_id"], dict):
            doc = self.documents.get(query["_id"])
            return deepcopy(doc) if doc else None
        for doc in self.documents.values():
            if all(doc.get(key) == value for key, value in query.items()):
                return deepcopy(doc)
        return None

    async def update_one(self, query, update, upsert=False):
        key = query.get("_id")
        doc = self.documents.get(key)
        if doc is None and upsert:
            doc = {"_id": key}
            doc.update(deepcopy(update.get("$setOnInsert", {})))
            self.documents[key] = doc
        elif doc is not None:
            doc.update(deepcopy(update.get("$set", {})))
        return type("Result", (), {"matched_count": 1 if doc else 0})()

    async def update_many(self, query, update):
        count = 0
        for doc in self.documents.values():
            if not doc.get("ldap_enabled"):
                continue
            if doc.get("ldap_profile_id") not in (None, ""):
                continue
            doc.update(deepcopy(update.get("$set", {})))
            count += 1
        return type("Result", (), {"modified_count": count})()


class FakeDatabase:
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.ldap_settings = MemoryCollection([
            {
                "_id": "global",
                "enabled": True,
                "host": "ldap.example.local",
                "port": 636,
                "use_ssl": True,
                "base_dn": "dc=example,dc=local",
                "bind_dn": "cn=dbachum,dc=example,dc=local",
                "bind_password_encrypted": "encrypted-secret",
                "ldif_template": "dn: cn=<USERNAME>,<BASE_DN>",
                "created_at": now,
                "updated_at": now,
            }
        ])
        self.ldap_profiles = MemoryCollection()
        self.provisioning_profiles = MemoryCollection([
            {
                "_id": "provisioning-1",
                "name": "ORMS User",
                "ldap_enabled": True,
            }
        ])


@pytest.mark.asyncio
async def test_global_ldap_settings_are_copied_without_destroying_original():
    database = FakeDatabase()

    await ensure_ldap_profiles_migrated(database)

    migrated = database.ldap_profiles.documents[LEGACY_LDAP_PROFILE_ID]
    legacy = database.ldap_settings.documents["global"]

    assert migrated["name"] == "Default LDAP"
    assert migrated["host"] == legacy["host"]
    assert migrated["bind_password_encrypted"] == "encrypted-secret"
    assert migrated["ldif_template"] == legacy["ldif_template"]
    assert migrated["migrated_from_legacy"] is True

    # The previous singleton is intentionally retained as rollback data.
    assert database.ldap_settings.documents["global"]["host"] == "ldap.example.local"

    # Existing LDAP-enabled provisioning profiles are wired to the migrated profile.
    assert (
        database.provisioning_profiles.documents["provisioning-1"]["ldap_profile_id"]
        == LEGACY_LDAP_PROFILE_ID
    )
