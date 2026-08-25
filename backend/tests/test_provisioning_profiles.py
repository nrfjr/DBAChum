import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.schemas.provisioning import (
    ProvisioningColumnMapping,
    ProvisioningProfileCreate,
    ProvisioningTableStep,
)
from app.services.database_connections import delete_database_connection
from app.services.provisioning import (
    list_provisioning_sources,
    validate_profile_dependencies,
)


class FindOneCollection:
    def __init__(self, value=None):
        self.value = value
        self.deleted = False

    async def find_one(self, *args, **kwargs):
        return self.value

    async def delete_one(self, *args, **kwargs):
        self.deleted = True
        return type("Result", (), {"deleted_count": 1})()


class ConnectionCollection:
    def __init__(self, documents):
        self.documents = documents
        self.deleted = False

    async def find_one(self, query, *args, **kwargs):
        object_id = query.get("_id")
        return self.documents.get(str(object_id))

    async def delete_one(self, query):
        self.deleted = True
        return type("Result", (), {"deleted_count": 1})()


class FakeDatabase:
    def __init__(self, connections=None, profile_reference=None, ldap=None):
        self.database_connections = ConnectionCollection(connections or {})
        self.provisioning_profiles = FindOneCollection(profile_reference)
        self.ldap_settings = FindOneCollection(ldap)


def test_mapping_normalizes_column_and_form_source():
    mapping = ProvisioningColumnMapping(
        column_name=" user_name ",
        value_kind="form",
        value_key="first_name",
    )

    assert mapping.column_name == "USER_NAME"
    assert mapping.value_key == "first_name"
    assert mapping.custom_value is None


def test_custom_mapping_requires_value():
    with pytest.raises(ValidationError):
        ProvisioningColumnMapping(
            column_name="STATUS",
            value_kind="custom",
            custom_value=None,
        )


def test_table_step_requires_one_inserted_column():
    with pytest.raises(ValidationError):
        ProvisioningTableStep(
            name="USER_MASTER",
            connection_id="a" * 24,
            owner="ORMS",
            table_name="USER_MASTER",
            mappings=[
                ProvisioningColumnMapping(
                    column_name="DESCRIPTION",
                    value_kind="omit",
                )
            ],
        )


def test_profile_supports_user_master_as_normal_table_step():
    profile = ProvisioningProfileCreate(
        name="ORMS User",
        schema_connection_id="a" * 24,
        ldap_enabled=True,
        table_steps=[
            {
                "name": "Insert USER_MASTER",
                "connection_id": "b" * 24,
                "owner": "ORMS",
                "table_name": "USER_MASTER",
                "mappings": [
                    {
                        "column_name": "USERNAME",
                        "value_kind": "generated",
                        "value_key": "username",
                    },
                    {
                        "column_name": "STATUS",
                        "value_kind": "custom",
                        "custom_value": "ACTIVE",
                    },
                ],
            }
        ],
    )

    assert profile.table_steps[0].table_name == "USER_MASTER"
    assert profile.table_steps[0].mappings[1].custom_value == "ACTIVE"


def test_source_catalog_exposes_form_and_generated_values():
    sources = list_provisioning_sources()
    keys = {(item["kind"], item["key"]) for item in sources}

    assert ("form", "first_name") in keys
    assert ("form", "reference_user") in keys
    assert ("generated", "username") in keys
    assert ("generated", "password") in keys


@pytest.mark.asyncio
async def test_ldap_is_optional_when_profile_opts_out():
    database = FakeDatabase(
        connections={
            "a" * 24: {"engine": "oracle", "enabled": True},
        },
        ldap=None,
    )

    issues = await validate_profile_dependencies(
        database,
        {
            "schema_connection_id": "a" * 24,
            "ldap_enabled": False,
            "table_steps": [],
        },
    )

    assert issues == []


@pytest.mark.asyncio
async def test_ldap_opt_in_is_not_ready_without_global_configuration():
    database = FakeDatabase(
        connections={
            "a" * 24: {"engine": "oracle", "enabled": True},
        },
        ldap=None,
    )

    issues = await validate_profile_dependencies(
        database,
        {
            "schema_connection_id": "a" * 24,
            "ldap_enabled": True,
            "table_steps": [],
        },
    )

    assert "LDAP is enabled for this profile but LDAP settings are incomplete." in issues


@pytest.mark.asyncio
async def test_missing_table_connection_marks_profile_not_ready():
    database = FakeDatabase(
        connections={
            "a" * 24: {"engine": "oracle", "enabled": True},
        }
    )

    issues = await validate_profile_dependencies(
        database,
        {
            "schema_connection_id": "a" * 24,
            "ldap_enabled": False,
            "table_steps": [
                {"connection_id": "b" * 24}
            ],
        },
    )

    assert "Table step 1 connection is missing." in issues


@pytest.mark.asyncio
async def test_connection_delete_is_blocked_when_profile_depends_on_it():
    database = FakeDatabase(
        connections={"a" * 24: {"engine": "oracle", "enabled": True}},
        profile_reference={"name": "ORMS User"},
    )

    with pytest.raises(AppError) as exc_info:
        await delete_database_connection(database, "a" * 24)

    assert exc_info.value.code == "CONNECTION_IN_USE_BY_PROVISIONING"
    assert database.database_connections.deleted is False
