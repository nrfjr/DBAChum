from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.connectors.oracle_metadata import (
    list_oracle_columns,
    list_oracle_schemas,
    list_oracle_tables,
)
from app.core.exceptions import AppError
from app.core.security import encrypt_secret
from app.schemas.provisioning import (
    LdapSettingsResponse,
    LdapSettingsUpdate,
    ProvisioningProfileCreate,
    ProvisioningProfileResponse,
    ProvisioningProfileUpdate,
)
from app.services.database_connections import get_database_connection


FORM_SOURCE_OPTIONS = [
    {"key": "first_name", "label": "First name", "kind": "form"},
    {"key": "middle_name", "label": "Middle name", "kind": "form"},
    {"key": "last_name", "label": "Last name", "kind": "form"},
    {"key": "employee_id", "label": "Employee ID", "kind": "form"},
    {"key": "reference_user", "label": "Reference user", "kind": "form"},
    {"key": "requestor", "label": "Requestor", "kind": "form"},
    {"key": "request_reference", "label": "Request / ticket", "kind": "form"},
]

GENERATED_SOURCE_OPTIONS = [
    {"key": "username", "label": "Generated username", "kind": "generated"},
    {"key": "password", "label": "Provisioned password", "kind": "generated"},
    {"key": "operator_username", "label": "Current DBAChum user", "kind": "generated"},
    {"key": "current_datetime", "label": "Current date/time", "kind": "generated"},
]


def normalize_profile_name(name: str) -> str:
    return name.strip().lower()


def parse_profile_id(profile_id: str) -> ObjectId:
    try:
        return ObjectId(profile_id)
    except Exception:
        raise AppError(
            "Provisioning profile not found.",
            code="PROVISIONING_PROFILE_NOT_FOUND",
            status_code=404,
        )


async def _validate_oracle_connection(database, connection_id: str, label: str) -> dict:
    connection = await get_database_connection(database, connection_id)

    if connection.get("engine") != "oracle":
        raise AppError(
            f"{label} must use an Oracle connection.",
            code="PROVISIONING_ORACLE_CONNECTION_REQUIRED",
            status_code=400,
        )

    return connection


async def validate_profile_dependencies(database, profile: dict) -> list[str]:
    issues: list[str] = []

    try:
        schema_connection = await get_database_connection(
            database,
            profile["schema_connection_id"],
        )
        if schema_connection.get("engine") != "oracle":
            issues.append("Schema creation connection is not Oracle.")
        elif not schema_connection.get("enabled", True):
            issues.append("Schema creation connection is disabled.")
    except AppError:
        issues.append("Schema creation connection is missing.")

    for index, step in enumerate(profile.get("table_steps") or [], start=1):
        try:
            connection = await get_database_connection(database, step["connection_id"])
            if connection.get("engine") != "oracle":
                issues.append(f"Table step {index} does not use an Oracle connection.")
            elif not connection.get("enabled", True):
                issues.append(f"Table step {index} uses a disabled connection.")
        except AppError:
            issues.append(f"Table step {index} connection is missing.")

    if profile.get("ldap_enabled"):
        ldap = await database.ldap_settings.find_one({"_id": "global"})
        if not ldap or not ldap.get("enabled") or not ldap.get("bind_password_encrypted"):
            issues.append("LDAP is enabled for this profile but LDAP settings are incomplete.")

    return issues


async def profile_to_response(database, document: dict) -> ProvisioningProfileResponse:
    issues = await validate_profile_dependencies(database, document)
    return ProvisioningProfileResponse(
        id=str(document["_id"]),
        name=document["name"],
        description=document.get("description"),
        schema_connection_id=document["schema_connection_id"],
        ldap_enabled=document.get("ldap_enabled", False),
        enabled=document.get("enabled", True),
        table_steps=document.get("table_steps", []),
        ready=len(issues) == 0,
        issues=issues,
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )


async def list_provisioning_profiles(database):
    documents = await database.provisioning_profiles.find().sort("name", 1).to_list(None)
    return [await profile_to_response(database, document) for document in documents]


async def get_provisioning_profile(database, profile_id: str):
    document = await database.provisioning_profiles.find_one(
        {"_id": parse_profile_id(profile_id)}
    )
    if document is None:
        raise AppError(
            "Provisioning profile not found.",
            code="PROVISIONING_PROFILE_NOT_FOUND",
            status_code=404,
        )
    return document


async def _validate_profile_connections(database, data):
    await _validate_oracle_connection(
        database,
        data.schema_connection_id,
        "Schema creation connection",
    )
    for step in data.table_steps:
        await _validate_oracle_connection(
            database,
            step.connection_id,
            f'Table step "{step.name}" connection',
        )


async def create_provisioning_profile(database, data: ProvisioningProfileCreate):
    await _validate_profile_connections(database, data)
    now = datetime.now(timezone.utc)
    document = data.model_dump(mode="json")
    document.update(
        {
            "name_key": normalize_profile_name(data.name),
            "created_at": now,
            "updated_at": now,
        }
    )
    try:
        result = await database.provisioning_profiles.insert_one(document)
    except DuplicateKeyError:
        raise AppError(
            "A provisioning profile with this name already exists.",
            code="PROVISIONING_PROFILE_NAME_EXISTS",
            status_code=409,
        )
    created = await database.provisioning_profiles.find_one({"_id": result.inserted_id})
    return await profile_to_response(database, created)


async def update_provisioning_profile(
    database,
    profile_id: str,
    data: ProvisioningProfileUpdate,
):
    object_id = parse_profile_id(profile_id)
    existing = await database.provisioning_profiles.find_one({"_id": object_id})
    if existing is None:
        raise AppError(
            "Provisioning profile not found.",
            code="PROVISIONING_PROFILE_NOT_FOUND",
            status_code=404,
        )
    await _validate_profile_connections(database, data)
    document = data.model_dump(mode="json")
    document["name_key"] = normalize_profile_name(data.name)
    document["updated_at"] = datetime.now(timezone.utc)
    try:
        await database.provisioning_profiles.update_one(
            {"_id": object_id}, {"$set": document}
        )
    except DuplicateKeyError:
        raise AppError(
            "A provisioning profile with this name already exists.",
            code="PROVISIONING_PROFILE_NAME_EXISTS",
            status_code=409,
        )
    updated = await database.provisioning_profiles.find_one({"_id": object_id})
    return await profile_to_response(database, updated)


async def delete_provisioning_profile(database, profile_id: str):
    result = await database.provisioning_profiles.delete_one(
        {"_id": parse_profile_id(profile_id)}
    )
    if result.deleted_count == 0:
        raise AppError(
            "Provisioning profile not found.",
            code="PROVISIONING_PROFILE_NOT_FOUND",
            status_code=404,
        )


async def get_ldap_settings(database) -> LdapSettingsResponse:
    document = await database.ldap_settings.find_one({"_id": "global"})
    if document is None:
        return LdapSettingsResponse(
            configured=False,
            enabled=False,
            host="",
            port=636,
            use_ssl=True,
            base_dn="",
            bind_dn="",
            has_bind_password=False,
            updated_at=None,
        )
    return LdapSettingsResponse(
        configured=bool(
            document.get("host")
            and document.get("base_dn")
            and document.get("bind_dn")
            and document.get("bind_password_encrypted")
        ),
        enabled=document.get("enabled", False),
        host=document.get("host", ""),
        port=document.get("port", 636),
        use_ssl=document.get("use_ssl", True),
        base_dn=document.get("base_dn", ""),
        bind_dn=document.get("bind_dn", ""),
        has_bind_password=bool(document.get("bind_password_encrypted")),
        updated_at=document.get("updated_at"),
    )


async def update_ldap_settings(database, data: LdapSettingsUpdate):
    existing = await database.ldap_settings.find_one({"_id": "global"}) or {}
    document = data.model_dump(mode="json")
    password = document.pop("bind_password", None)

    if data.enabled and not password and not existing.get("bind_password_encrypted"):
        raise AppError(
            "LDAP bind password is required when enabling LDAP.",
            code="LDAP_BIND_PASSWORD_REQUIRED",
            status_code=400,
        )

    if password:
        document["bind_password_encrypted"] = encrypt_secret(password)

    document["updated_at"] = datetime.now(timezone.utc)
    await database.ldap_settings.update_one(
        {"_id": "global"},
        {"$set": document, "$setOnInsert": {"created_at": document["updated_at"]}},
        upsert=True,
    )
    return await get_ldap_settings(database)


async def get_metadata_connection(database, connection_id: str) -> dict:
    connection = await _validate_oracle_connection(
        database,
        connection_id,
        "Metadata connection",
    )
    if not connection.get("enabled", True):
        raise AppError(
            "The selected Oracle connection is disabled.",
            code="PROVISIONING_CONNECTION_DISABLED",
            status_code=400,
        )
    return connection


async def load_oracle_schemas(database, connection_id: str):
    return await list_oracle_schemas(await get_metadata_connection(database, connection_id))


async def load_oracle_tables(database, connection_id: str, owner: str):
    return await list_oracle_tables(
        await get_metadata_connection(database, connection_id), owner
    )


async def load_oracle_columns(
    database,
    connection_id: str,
    owner: str,
    table_name: str,
):
    return await list_oracle_columns(
        await get_metadata_connection(database, connection_id), owner, table_name
    )


def list_provisioning_sources():
    return [*FORM_SOURCE_OPTIONS, *GENERATED_SOURCE_OPTIONS]
