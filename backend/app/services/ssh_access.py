from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppError
from app.core.security import encrypt_secret
from app.schemas.ssh_access import (
    SshAccessProfileCreate,
    SshAccessProfileResponse,
    SshAccessProfileUpdate,
    SshAuthType,
)


def normalize_ssh_profile_name(name: str) -> str:
    return name.strip().lower()


def parse_ssh_profile_id(profile_id: str) -> ObjectId:
    try:
        return ObjectId(profile_id)
    except Exception:
        raise AppError(
            "SSH access profile not found.",
            code="SSH_PROFILE_NOT_FOUND",
            status_code=404,
        )


async def ssh_profile_to_response(database, profile: dict) -> SshAccessProfileResponse:
    profile_id = str(profile["_id"])
    server_count = await database.servers.count_documents(
        {"ssh_profile_id": profile_id}
    )

    return SshAccessProfileResponse(
        id=profile_id,
        name=profile["name"],
        username=profile["username"],
        port=profile.get("port", 22),
        auth_type=profile.get("auth_type", SshAuthType.PASSWORD.value),
        notes=profile.get("notes"),
        enabled=profile.get("enabled", True),
        has_password=bool(profile.get("password_encrypted")),
        has_private_key=bool(profile.get("private_key_encrypted")),
        has_passphrase=bool(profile.get("passphrase_encrypted")),
        server_count=server_count,
        created_at=profile["created_at"],
        updated_at=profile["updated_at"],
    )


async def list_ssh_profiles(database):
    profiles = await database.ssh_access_profiles.find().sort("name", 1).to_list(None)
    return [await ssh_profile_to_response(database, profile) for profile in profiles]


async def get_ssh_profile(database, profile_id: str):
    object_id = parse_ssh_profile_id(profile_id)
    profile = await database.ssh_access_profiles.find_one({"_id": object_id})
    if profile is None:
        raise AppError(
            "SSH access profile not found.",
            code="SSH_PROFILE_NOT_FOUND",
            status_code=404,
        )
    return profile


def _secret_updates(data, existing: dict | None = None) -> dict:
    updates: dict[str, str] = {}

    if data.password is not None:
        updates["password_encrypted"] = encrypt_secret(data.password)
    if data.private_key is not None:
        updates["private_key_encrypted"] = encrypt_secret(data.private_key)
    if data.passphrase is not None:
        updates["passphrase_encrypted"] = encrypt_secret(data.passphrase)

    auth_type = data.auth_type.value
    existing = existing or {}

    if auth_type == SshAuthType.PASSWORD.value:
        has_secret = bool(updates.get("password_encrypted") or existing.get("password_encrypted"))
        if not has_secret:
            raise AppError(
                "Password authentication requires a stored password.",
                code="SSH_PASSWORD_REQUIRED",
                status_code=400,
            )
    else:
        has_secret = bool(updates.get("private_key_encrypted") or existing.get("private_key_encrypted"))
        if not has_secret:
            raise AppError(
                "Private-key authentication requires a stored private key.",
                code="SSH_PRIVATE_KEY_REQUIRED",
                status_code=400,
            )

    return updates


async def create_ssh_profile(database, data: SshAccessProfileCreate):
    now = datetime.now(timezone.utc)
    document = data.model_dump(
        mode="json",
        exclude={"password", "private_key", "passphrase"},
    )
    document["name_key"] = normalize_ssh_profile_name(data.name)
    document.update(_secret_updates(data))
    document.update({"created_at": now, "updated_at": now})

    try:
        result = await database.ssh_access_profiles.insert_one(document)
    except DuplicateKeyError:
        raise AppError(
            "An SSH access profile with this name already exists.",
            code="SSH_PROFILE_NAME_EXISTS",
            status_code=409,
        )

    profile = await database.ssh_access_profiles.find_one({"_id": result.inserted_id})
    return await ssh_profile_to_response(database, profile)


async def update_ssh_profile(
    database,
    profile_id: str,
    data: SshAccessProfileUpdate,
):
    object_id = parse_ssh_profile_id(profile_id)
    existing = await get_ssh_profile(database, profile_id)

    document = data.model_dump(
        mode="json",
        exclude={"password", "private_key", "passphrase"},
    )
    document["name_key"] = normalize_ssh_profile_name(data.name)
    document.update(_secret_updates(data, existing))
    document["updated_at"] = datetime.now(timezone.utc)

    try:
        result = await database.ssh_access_profiles.update_one(
            {"_id": object_id},
            {"$set": document},
        )
    except DuplicateKeyError:
        raise AppError(
            "An SSH access profile with this name already exists.",
            code="SSH_PROFILE_NAME_EXISTS",
            status_code=409,
        )

    if result.matched_count == 0:
        raise AppError(
            "SSH access profile not found.",
            code="SSH_PROFILE_NOT_FOUND",
            status_code=404,
        )

    profile = await database.ssh_access_profiles.find_one({"_id": object_id})
    return await ssh_profile_to_response(database, profile)


async def delete_ssh_profile(database, profile_id: str):
    object_id = parse_ssh_profile_id(profile_id)

    in_use = await database.servers.find_one(
        {"ssh_profile_id": profile_id},
        {"name": 1},
    )
    if in_use is not None:
        raise AppError(
            f'This SSH access profile is used by server "{in_use.get("name", "Unnamed server")}".',
            code="SSH_PROFILE_IN_USE",
            status_code=409,
        )

    result = await database.ssh_access_profiles.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise AppError(
            "SSH access profile not found.",
            code="SSH_PROFILE_NOT_FOUND",
            status_code=404,
        )
