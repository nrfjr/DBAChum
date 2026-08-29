from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppError
from app.schemas.server import ServerCreate, ServerResponse, ServerUpdate


def normalize_server_name(name: str) -> str:
    return name.strip().lower()


def parse_server_id(server_id: str) -> ObjectId:
    try:
        return ObjectId(server_id)
    except Exception:
        raise AppError(
            "Server not found.",
            code="SERVER_NOT_FOUND",
            status_code=404,
        )


async def _validate_ssh_profile(database, ssh_profile_id: str | None) -> None:
    if not ssh_profile_id:
        return
    try:
        object_id = ObjectId(ssh_profile_id)
    except Exception:
        raise AppError(
            "Selected SSH access profile is invalid.",
            code="INVALID_SSH_PROFILE",
            status_code=400,
        )

    exists = await database.ssh_access_profiles.count_documents({"_id": object_id})
    if not exists:
        raise AppError(
            "Selected SSH access profile does not exist.",
            code="SSH_PROFILE_NOT_FOUND",
            status_code=400,
        )


async def _validate_database_connection_ids(database, connection_ids: list[str]) -> list[ObjectId]:
    if not connection_ids:
        return []

    object_ids: list[ObjectId] = []
    for connection_id in connection_ids:
        try:
            object_ids.append(ObjectId(connection_id))
        except Exception:
            raise AppError(
                "One or more selected database connections are invalid.",
                code="INVALID_DATABASE_RELATIONSHIP",
                status_code=400,
            )

    count = await database.database_connections.count_documents({"_id": {"$in": object_ids}})
    if count != len(object_ids):
        raise AppError(
            "One or more selected database connections do not exist.",
            code="DATABASE_RELATIONSHIP_NOT_FOUND",
            status_code=400,
        )
    return object_ids


async def _set_database_relationships(database, server_id: str, connection_ids: list[str]) -> None:
    object_ids = await _validate_database_connection_ids(database, connection_ids)

    await database.database_connections.update_many(
        {"server_ids": server_id},
        {"$pull": {"server_ids": server_id}},
    )

    if object_ids:
        await database.database_connections.update_many(
            {"_id": {"$in": object_ids}},
            {"$addToSet": {"server_ids": server_id}},
        )


async def _relationship_ids(database, server_id: str) -> list[str]:
    cursor = database.database_connections.find(
        {"server_ids": server_id},
        {"_id": 1},
    ).sort("name", 1)
    docs = await cursor.to_list(None)
    return [str(item["_id"]) for item in docs]


async def server_to_response(database, server: dict) -> ServerResponse:
    server_id = str(server["_id"])
    database_connection_ids = await _relationship_ids(database, server_id)

    ssh_profile_name = None
    ssh_profile_id = server.get("ssh_profile_id")
    if ssh_profile_id:
        try:
            ssh_profile = await database.ssh_access_profiles.find_one(
                {"_id": ObjectId(ssh_profile_id)},
                {"name": 1},
            )
        except Exception:
            ssh_profile = None
        if ssh_profile:
            ssh_profile_name = ssh_profile.get("name")

    return ServerResponse(
        id=server_id,
        name=server["name"],
        hostname=server["hostname"],
        ip_address=server.get("ip_address"),
        server_type=server.get("server_type", "database"),
        os_family=server["os_family"],
        os_version=server.get("os_version"),
        environment=server.get("environment"),
        owner=server.get("owner"),
        tags=server.get("tags", []),
        notes=server.get("notes"),
        ssh_profile_id=ssh_profile_id,
        ssh_profile_name=ssh_profile_name,
        ssh_host_key_fingerprint=server.get("ssh_host_key_fingerprint"),
        ssh_host_key_trusted_at=server.get("ssh_host_key_trusted_at"),
        database_connection_ids=database_connection_ids,
        enabled=server.get("enabled", True),
        database_count=len(database_connection_ids),
        created_at=server["created_at"],
        updated_at=server["updated_at"],
    )


async def list_servers(database):
    servers = await database.servers.find().sort("name", 1).to_list(None)
    return [await server_to_response(database, server) for server in servers]


async def get_server(database, server_id: str):
    object_id = parse_server_id(server_id)
    server = await database.servers.find_one({"_id": object_id})
    if server is None:
        raise AppError(
            "Server not found.",
            code="SERVER_NOT_FOUND",
            status_code=404,
        )
    return server


async def create_server(database, data: ServerCreate):
    await _validate_ssh_profile(database, data.ssh_profile_id)
    await _validate_database_connection_ids(database, data.database_connection_ids)

    now = datetime.now(timezone.utc)
    document = data.model_dump(mode="json", exclude={"database_connection_ids"})
    document.update(
        {
            "name_key": normalize_server_name(data.name),
            "created_at": now,
            "updated_at": now,
        }
    )

    try:
        result = await database.servers.insert_one(document)
    except DuplicateKeyError:
        raise AppError(
            "A server with this name already exists.",
            code="SERVER_NAME_EXISTS",
            status_code=409,
        )

    server_id = str(result.inserted_id)
    await _set_database_relationships(database, server_id, data.database_connection_ids)
    server = await database.servers.find_one({"_id": result.inserted_id})
    return await server_to_response(database, server)


async def update_server(database, server_id: str, data: ServerUpdate):
    object_id = parse_server_id(server_id)
    existing = await get_server(database, server_id)
    await _validate_ssh_profile(database, data.ssh_profile_id)
    await _validate_database_connection_ids(database, data.database_connection_ids)

    document = data.model_dump(mode="json", exclude={"database_connection_ids"})
    document["name_key"] = normalize_server_name(data.name)
    document["updated_at"] = datetime.now(timezone.utc)

    endpoint_changed = (
        existing.get("hostname") != data.hostname
        or existing.get("ip_address") != data.ip_address
        or existing.get("ssh_profile_id") != data.ssh_profile_id
    )
    update_document: dict = {"$set": document}
    if endpoint_changed:
        update_document["$unset"] = {
            "ssh_host_key_fingerprint": "",
            "ssh_host_key_trusted_at": "",
        }

    try:
        result = await database.servers.update_one(
            {"_id": object_id},
            update_document,
        )
    except DuplicateKeyError:
        raise AppError(
            "A server with this name already exists.",
            code="SERVER_NAME_EXISTS",
            status_code=409,
        )

    if result.matched_count == 0:
        raise AppError(
            "Server not found.",
            code="SERVER_NOT_FOUND",
            status_code=404,
        )

    await _set_database_relationships(database, server_id, data.database_connection_ids)
    server = await database.servers.find_one({"_id": object_id})
    return await server_to_response(database, server)


async def delete_server(database, server_id: str):
    object_id = parse_server_id(server_id)
    result = await database.servers.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise AppError(
            "Server not found.",
            code="SERVER_NOT_FOUND",
            status_code=404,
        )

    await database.database_connections.update_many(
        {"server_ids": server_id},
        {"$pull": {"server_ids": server_id}},
    )


async def list_server_databases(database, server_id: str):
    await get_server(database, server_id)
    cursor = database.database_connections.find({"server_ids": server_id}).sort("name", 1)
    return await cursor.to_list(None)
