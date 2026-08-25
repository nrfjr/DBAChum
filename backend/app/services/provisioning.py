import asyncio
from datetime import datetime, timezone

from bson import ObjectId
from ldap3 import BASE, Connection, Server
from pymongo.errors import DuplicateKeyError

from app.connectors.oracle_metadata import (
    list_oracle_columns,
    list_oracle_schemas,
    list_oracle_sequences,
    list_oracle_tables,
)
from app.core.exceptions import AppError
from app.core.security import decrypt_secret, encrypt_secret
from app.schemas.provisioning import (
    LdapProfileCreate,
    LdapProfileResponse,
    LdapProfileTestResponse,
    LdapProfileUpdate,
    LdapSettingsResponse,
    LdapSettingsUpdate,
    ProvisioningProfileCreate,
    ProvisioningProfileResponse,
    ProvisioningProfileUpdate,
)
from app.services.database_connections import (
    connection_is_active,
    connection_is_monitored,
    get_database_connection,
)
from app.services.ldap_ldif import DEFAULT_LDIF_TEMPLATE


LEGACY_LDAP_PROFILE_ID = "global"
LEGACY_LDAP_PROFILE_NAME = "Default LDAP"

FORM_SOURCE_OPTIONS = [
    {"key": "first_name", "label": "First name", "kind": "form"},
    {"key": "middle_name", "label": "Middle name", "kind": "form"},
    {"key": "last_name", "label": "Last name", "kind": "form"},
    {"key": "employee_id", "label": "Employee ID", "kind": "form"},
    {"key": "reference_user", "label": "Reference user", "kind": "form"},
    {"key": "requestor", "label": "Requestor", "kind": "form"},
    {"key": "request_reference", "label": "Request / ticket", "kind": "form"},
    {"key": "remarks", "label": "Remarks", "kind": "form"},
]

GENERATED_SOURCE_OPTIONS = [
    {"key": "username", "label": "Generated username", "kind": "generated"},
    {"key": "password", "label": "Provisioned password (generated or custom)", "kind": "generated"},
    {"key": "operator_username", "label": "Current DBAChum user", "kind": "generated"},
    {"key": "requester_ip", "label": "Requester machine IP", "kind": "generated"},
    {"key": "current_datetime", "label": "Current date/time", "kind": "generated"},
]


def normalize_profile_name(name: str) -> str:
    return name.strip().lower()


def effective_match_columns(step: dict) -> list[str]:
    configured = [
        str(column).strip().upper()
        for column in (step.get("match_columns") or [])
        if str(column).strip()
    ]
    if configured:
        return configured

    # Backward-compatible inference for profiles created before Phase 4A added
    # explicit upsert keys. Generated username is the canonical cross-system
    # identity in DBAChum, so a single such mapping is safe to infer.
    inferred = [
        str(mapping.get("column_name", "")).strip().upper()
        for mapping in (step.get("mappings") or [])
        if mapping.get("value_kind") == "generated"
        and mapping.get("value_key") == "username"
        and str(mapping.get("column_name", "")).strip()
    ]
    return inferred if len(inferred) == 1 else []


def parse_profile_id(profile_id: str) -> ObjectId:
    try:
        return ObjectId(profile_id)
    except Exception:
        raise AppError(
            "Provisioning profile not found.",
            code="PROVISIONING_PROFILE_NOT_FOUND",
            status_code=404,
        )


def ldap_profile_database_id(profile_id: str):
    if profile_id == LEGACY_LDAP_PROFILE_ID:
        return LEGACY_LDAP_PROFILE_ID
    try:
        return ObjectId(profile_id)
    except Exception:
        raise AppError(
            "LDAP profile not found.",
            code="LDAP_PROFILE_NOT_FOUND",
            status_code=404,
        )


async def ensure_ldap_profiles_migrated(database):
    """Non-destructively migrate the old singleton LDAP record.

    The old ldap_settings/global document is deliberately retained as a rollback
    copy. A stable ldap_profiles/global document is created once, and existing
    provisioning profiles that merely had ldap_enabled=true are pointed at it.
    """
    existing = await database.ldap_profiles.find_one({"_id": LEGACY_LDAP_PROFILE_ID})
    if existing is None:
        legacy = await database.ldap_settings.find_one({"_id": "global"})
        if legacy is not None:
            now = datetime.now(timezone.utc)
            migrated = {
                "_id": LEGACY_LDAP_PROFILE_ID,
                "name": LEGACY_LDAP_PROFILE_NAME,
                "name_key": normalize_profile_name(LEGACY_LDAP_PROFILE_NAME),
                "description": "Migrated automatically from the previous global LDAP settings.",
                "enabled": legacy.get("enabled", False),
                "host": legacy.get("host", ""),
                "port": legacy.get("port", 636),
                "use_ssl": legacy.get("use_ssl", True),
                "base_dn": legacy.get("base_dn", ""),
                "bind_dn": legacy.get("bind_dn", ""),
                "bind_password_encrypted": legacy.get("bind_password_encrypted"),
                "ldif_template": legacy.get("ldif_template") or DEFAULT_LDIF_TEMPLATE,
                "migrated_from_legacy": True,
                "created_at": legacy.get("created_at") or now,
                "updated_at": legacy.get("updated_at") or now,
            }
            try:
                await database.ldap_profiles.update_one(
                    {"_id": LEGACY_LDAP_PROFILE_ID},
                    {"$setOnInsert": migrated},
                    upsert=True,
                )
            except DuplicateKeyError:
                # Parallel Settings/Provisioning loads can race on first migration.
                # The stable _id means the other request already created the same profile.
                pass
            existing = await database.ldap_profiles.find_one(
                {"_id": LEGACY_LDAP_PROFILE_ID}
            )

    if existing is not None:
        await database.provisioning_profiles.update_many(
            {
                "ldap_enabled": True,
                "$or": [
                    {"ldap_profile_id": {"$exists": False}},
                    {"ldap_profile_id": None},
                    {"ldap_profile_id": ""},
                ],
            },
            {
                "$set": {
                    "ldap_profile_id": LEGACY_LDAP_PROFILE_ID,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )


async def _validate_oracle_connection(
    database,
    connection_id: str,
    label: str,
    *,
    require_monitored: bool = False,
) -> dict:
    connection = await get_database_connection(database, connection_id)

    if connection.get("engine") != "oracle":
        raise AppError(
            f"{label} must use an Oracle connection.",
            code="PROVISIONING_ORACLE_CONNECTION_REQUIRED",
            status_code=400,
        )
    if not connection_is_active(connection):
        raise AppError(
            f"{label} is disabled.",
            code="PROVISIONING_CONNECTION_DISABLED",
            status_code=400,
        )
    if require_monitored and not connection_is_monitored(connection):
        raise AppError(
            f"{label} must be a monitored database connection so the profile has a Users & Schemas parent workspace.",
            code="PROVISIONING_PARENT_NOT_MONITORED",
            status_code=400,
        )

    return connection


async def get_ldap_profile_document(database, profile_id: str) -> dict:
    await ensure_ldap_profiles_migrated(database)
    document = await database.ldap_profiles.find_one(
        {"_id": ldap_profile_database_id(profile_id)}
    )
    if document is None:
        raise AppError(
            "LDAP profile not found.",
            code="LDAP_PROFILE_NOT_FOUND",
            status_code=404,
        )
    return document


async def validate_profile_dependencies(database, profile: dict) -> list[str]:
    issues: list[str] = []

    try:
        schema_connection = await get_database_connection(
            database,
            profile["schema_connection_id"],
        )
        if schema_connection.get("engine") != "oracle":
            issues.append("Parent database connection is not Oracle.")
        elif not connection_is_active(schema_connection):
            issues.append("Parent database connection is disabled.")
        elif not connection_is_monitored(schema_connection):
            issues.append(
                "Parent database connection is not monitored, so the profile has no Users & Schemas workspace."
            )
    except AppError:
        issues.append("Parent database connection is missing.")

    for index, step in enumerate(profile.get("table_steps") or [], start=1):
        try:
            connection = await get_database_connection(database, step["connection_id"])
            if connection.get("engine") != "oracle":
                issues.append(f"Table step {index} does not use an Oracle connection.")
            elif not connection_is_active(connection):
                issues.append(f"Table step {index} uses a disabled connection.")
        except AppError:
            issues.append(f"Table step {index} connection is missing.")

        if not effective_match_columns(step):
            issues.append(
                f"Table step {index} needs at least one upsert match column."
            )

    if profile.get("ldap_enabled"):
        ldap_profile_id = profile.get("ldap_profile_id")
        if not ldap_profile_id:
            # Old records are supported until ensure_ldap_profiles_migrated() runs.
            legacy = await database.ldap_settings.find_one({"_id": "global"})
            if not legacy or not legacy.get("enabled") or not legacy.get("bind_password_encrypted"):
                issues.append("LDAP is enabled but no LDAP profile is selected.")
        else:
            try:
                ldap = await get_ldap_profile_document(database, ldap_profile_id)
                if not ldap.get("enabled"):
                    issues.append("Selected LDAP profile is disabled.")
                elif not (
                    ldap.get("host")
                    and ldap.get("base_dn")
                    and ldap.get("bind_dn")
                    and ldap.get("bind_password_encrypted")
                ):
                    issues.append("Selected LDAP profile is incomplete.")
            except AppError:
                issues.append("Selected LDAP profile is missing.")

    return issues


async def profile_to_response(database, document: dict) -> ProvisioningProfileResponse:
    issues = await validate_profile_dependencies(database, document)
    return ProvisioningProfileResponse(
        id=str(document["_id"]),
        name=document["name"],
        description=document.get("description"),
        schema_connection_id=document["schema_connection_id"],
        ldap_enabled=document.get("ldap_enabled", False),
        ldap_profile_id=document.get("ldap_profile_id"),
        enabled=document.get("enabled", True),
        table_steps=document.get("table_steps", []),
        ready=len(issues) == 0,
        issues=issues,
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )


async def list_provisioning_profiles(database):
    await ensure_ldap_profiles_migrated(database)
    documents = await database.provisioning_profiles.find().sort("name", 1).to_list(None)
    return [await profile_to_response(database, document) for document in documents]


async def list_provisioning_profiles_for_connection(
    database,
    connection_id: str,
):
    """Profiles visible from one parent database connection.

    The parent/schema connection is the database context that owns the profile.
    Table steps may still use separate application connections.
    """
    await ensure_ldap_profiles_migrated(database)
    # Validate the parent connection exists before returning child profiles.
    await _validate_oracle_connection(
        database,
        connection_id,
        "Parent database connection",
        require_monitored=True,
    )
    documents = await database.provisioning_profiles.find(
        {
            "schema_connection_id": connection_id,
            "enabled": {"$ne": False},
        }
    ).sort("name", 1).to_list(None)
    return [await profile_to_response(database, document) for document in documents]


async def get_provisioning_profile(database, profile_id: str):
    await ensure_ldap_profiles_migrated(database)
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
        "Parent database connection",
        require_monitored=True,
    )
    for step in data.table_steps:
        await _validate_oracle_connection(
            database,
            step.connection_id,
            f'Table step "{step.name}" connection',
        )

    if data.ldap_enabled:
        ldap = await get_ldap_profile_document(database, data.ldap_profile_id)
        if not ldap.get("enabled"):
            raise AppError(
                "The selected LDAP profile is disabled.",
                code="LDAP_PROFILE_DISABLED",
                status_code=400,
            )
        if not ldap.get("bind_password_encrypted"):
            raise AppError(
                "The selected LDAP profile does not have a bind password.",
                code="LDAP_PROFILE_INCOMPLETE",
                status_code=400,
            )


async def create_provisioning_profile(database, data: ProvisioningProfileCreate):
    await ensure_ldap_profiles_migrated(database)
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
    await ensure_ldap_profiles_migrated(database)
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


def ldap_profile_to_response(document: dict) -> LdapProfileResponse:
    return LdapProfileResponse(
        id=str(document["_id"]),
        name=document.get("name", LEGACY_LDAP_PROFILE_NAME),
        description=document.get("description"),
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
        ldif_template=document.get("ldif_template") or DEFAULT_LDIF_TEMPLATE,
        migrated_from_legacy=document.get("migrated_from_legacy", False),
        created_at=document.get("created_at"),
        updated_at=document.get("updated_at"),
    )


async def list_ldap_profiles(database):
    await ensure_ldap_profiles_migrated(database)
    documents = await database.ldap_profiles.find().sort("name", 1).to_list(None)
    return [ldap_profile_to_response(document) for document in documents]


async def _ensure_unique_ldap_name(database, name: str, exclude_id=None):
    query = {"name_key": normalize_profile_name(name)}
    if exclude_id is not None:
        query["_id"] = {"$ne": exclude_id}
    if await database.ldap_profiles.find_one(query):
        raise AppError(
            "An LDAP profile with this name already exists.",
            code="LDAP_PROFILE_NAME_EXISTS",
            status_code=409,
        )


async def create_ldap_profile(database, data: LdapProfileCreate):
    await ensure_ldap_profiles_migrated(database)
    await _ensure_unique_ldap_name(database, data.name)
    document = data.model_dump(mode="json")
    password = document.pop("bind_password", None)
    if data.enabled and not password:
        raise AppError(
            "LDAP bind password is required when enabling an LDAP profile.",
            code="LDAP_BIND_PASSWORD_REQUIRED",
            status_code=400,
        )
    if password:
        document["bind_password_encrypted"] = encrypt_secret(password)
    document["ldif_template"] = document.get("ldif_template") or DEFAULT_LDIF_TEMPLATE
    document["name_key"] = normalize_profile_name(data.name)
    now = datetime.now(timezone.utc)
    document["created_at"] = now
    document["updated_at"] = now
    result = await database.ldap_profiles.insert_one(document)
    created = await database.ldap_profiles.find_one({"_id": result.inserted_id})
    return ldap_profile_to_response(created)


async def update_ldap_profile(database, profile_id: str, data: LdapProfileUpdate):
    await ensure_ldap_profiles_migrated(database)
    database_id = ldap_profile_database_id(profile_id)
    existing = await database.ldap_profiles.find_one({"_id": database_id})
    if existing is None:
        raise AppError(
            "LDAP profile not found.",
            code="LDAP_PROFILE_NOT_FOUND",
            status_code=404,
        )
    await _ensure_unique_ldap_name(database, data.name, database_id)
    document = data.model_dump(mode="json")
    password = document.pop("bind_password", None)
    if data.enabled and not password and not existing.get("bind_password_encrypted"):
        raise AppError(
            "LDAP bind password is required when enabling an LDAP profile.",
            code="LDAP_BIND_PASSWORD_REQUIRED",
            status_code=400,
        )
    if password:
        document["bind_password_encrypted"] = encrypt_secret(password)
    document["ldif_template"] = document.get("ldif_template") or DEFAULT_LDIF_TEMPLATE
    document["name_key"] = normalize_profile_name(data.name)
    document["updated_at"] = datetime.now(timezone.utc)
    await database.ldap_profiles.update_one({"_id": database_id}, {"$set": document})
    updated = await database.ldap_profiles.find_one({"_id": database_id})
    return ldap_profile_to_response(updated)


async def delete_ldap_profile(database, profile_id: str):
    await ensure_ldap_profiles_migrated(database)
    if profile_id == LEGACY_LDAP_PROFILE_ID:
        raise AppError(
            "The migrated Default LDAP profile is retained for backward compatibility. Disable or edit it instead.",
            code="LDAP_MIGRATED_PROFILE_RETAINED",
            status_code=409,
        )
    referenced = await database.provisioning_profiles.find_one(
        {"ldap_enabled": True, "ldap_profile_id": profile_id}
    )
    if referenced:
        raise AppError(
            f'LDAP profile is used by provisioning profile "{referenced.get("name", "Unknown")}".',
            code="LDAP_PROFILE_IN_USE",
            status_code=409,
        )
    result = await database.ldap_profiles.delete_one(
        {"_id": ldap_profile_database_id(profile_id)}
    )
    if result.deleted_count == 0:
        raise AppError(
            "LDAP profile not found.",
            code="LDAP_PROFILE_NOT_FOUND",
            status_code=404,
        )


def _test_ldap_sync(document: dict) -> LdapProfileTestResponse:
    encrypted_password = document.get("bind_password_encrypted")
    if not encrypted_password:
        return LdapProfileTestResponse(
            success=False,
            connect_ok=False,
            bind_ok=False,
            base_dn_ok=False,
            message="LDAP profile does not have a saved bind password.",
        )

    password = decrypt_secret(encrypted_password)
    connection = None
    try:
        server = Server(
            document.get("host", ""),
            port=document.get("port", 636),
            use_ssl=document.get("use_ssl", True),
            connect_timeout=5,
        )
        connection = Connection(
            server,
            user=document.get("bind_dn", ""),
            password=password,
            receive_timeout=5,
            raise_exceptions=False,
        )

        connection.open()
        if connection.closed:
            return LdapProfileTestResponse(
                success=False,
                connect_ok=False,
                bind_ok=False,
                base_dn_ok=False,
                message="Unable to connect to the LDAP server.",
            )

        if not connection.bind():
            description = (connection.result or {}).get("description") or "bind failed"
            return LdapProfileTestResponse(
                success=False,
                connect_ok=True,
                bind_ok=False,
                base_dn_ok=False,
                message=f"LDAP server reached, but bind authentication failed ({description}).",
            )

        base_ok = connection.search(
            search_base=document.get("base_dn", ""),
            search_filter="(objectClass=*)",
            search_scope=BASE,
            attributes=[],
        )
        if not base_ok:
            description = (connection.result or {}).get("description") or "base DN lookup failed"
            return LdapProfileTestResponse(
                success=False,
                connect_ok=True,
                bind_ok=True,
                base_dn_ok=False,
                message=f"LDAP bind succeeded, but Base DN lookup failed ({description}).",
            )

        return LdapProfileTestResponse(
            success=True,
            connect_ok=True,
            bind_ok=True,
            base_dn_ok=True,
            message="LDAP connection, bind authentication, and Base DN lookup succeeded.",
        )
    except Exception as exc:
        return LdapProfileTestResponse(
            success=False,
            connect_ok=bool(connection and not connection.closed),
            bind_ok=bool(connection and connection.bound),
            base_dn_ok=False,
            message=f"LDAP test failed: {exc}",
        )
    finally:
        if connection is not None:
            try:
                connection.unbind()
            except Exception:
                pass


async def test_ldap_profile(database, profile_id: str):
    document = await get_ldap_profile_document(database, profile_id)
    if not (
        document.get("host")
        and document.get("base_dn")
        and document.get("bind_dn")
        and document.get("bind_password_encrypted")
    ):
        raise AppError(
            "Complete the LDAP host, Base DN, Bind DN, and saved Bind password before testing.",
            code="LDAP_PROFILE_INCOMPLETE",
            status_code=400,
        )
    return await asyncio.to_thread(_test_ldap_sync, document)


# Compatibility wrappers for the previous singleton API. They now target the
# migrated Default LDAP profile, so older UI/API clients do not suddenly break.
async def get_ldap_settings(database) -> LdapSettingsResponse:
    await ensure_ldap_profiles_migrated(database)
    document = await database.ldap_profiles.find_one({"_id": LEGACY_LDAP_PROFILE_ID})
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
            ldif_template=DEFAULT_LDIF_TEMPLATE,
            updated_at=None,
        )
    response = ldap_profile_to_response(document)
    return LdapSettingsResponse(
        configured=response.configured,
        enabled=response.enabled,
        host=response.host,
        port=response.port,
        use_ssl=response.use_ssl,
        base_dn=response.base_dn,
        bind_dn=response.bind_dn,
        has_bind_password=response.has_bind_password,
        ldif_template=response.ldif_template,
        updated_at=response.updated_at,
    )


async def update_ldap_settings(database, data: LdapSettingsUpdate):
    await ensure_ldap_profiles_migrated(database)
    existing = await database.ldap_profiles.find_one({"_id": LEGACY_LDAP_PROFILE_ID})
    if existing is None:
        now = datetime.now(timezone.utc)
        await database.ldap_profiles.insert_one(
            {
                "_id": LEGACY_LDAP_PROFILE_ID,
                "name": LEGACY_LDAP_PROFILE_NAME,
                "name_key": normalize_profile_name(LEGACY_LDAP_PROFILE_NAME),
                "description": "Default LDAP profile.",
                "enabled": False,
                "host": "",
                "port": 636,
                "use_ssl": True,
                "base_dn": "",
                "bind_dn": "",
                "ldif_template": DEFAULT_LDIF_TEMPLATE,
                "migrated_from_legacy": False,
                "created_at": now,
                "updated_at": now,
            }
        )
    await update_ldap_profile(
        database,
        LEGACY_LDAP_PROFILE_ID,
        LdapProfileUpdate(
            name=LEGACY_LDAP_PROFILE_NAME,
            description=(existing or {}).get("description"),
            enabled=data.enabled,
            host=data.host,
            port=data.port,
            use_ssl=data.use_ssl,
            base_dn=data.base_dn,
            bind_dn=data.bind_dn,
            bind_password=data.bind_password,
            ldif_template=data.ldif_template,
        ),
    )
    return await get_ldap_settings(database)


async def get_metadata_connection(database, connection_id: str) -> dict:
    connection = await _validate_oracle_connection(
        database,
        connection_id,
        "Metadata connection",
    )
    if not connection_is_active(connection):
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


async def load_oracle_sequences(database, connection_id: str, owner: str):
    return await list_oracle_sequences(
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
