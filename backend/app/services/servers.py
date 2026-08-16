from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppError
from app.schemas.server import (
    ServerCreate,
    ServerResponse,
    ServerUpdate,
)


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


async def server_to_response(
    database,
    server: dict,
) -> ServerResponse:
    server_id = str(server["_id"])

    database_count = (
        await database.database_connections.count_documents(
            {
                "server_ids": server_id,
            }
        )
    )

    return ServerResponse(
        id=server_id,
        name=server["name"],
        hostname=server["hostname"],
        ip_address=server.get("ip_address"),
        os_family=server["os_family"],
        os_version=server.get("os_version"),
        environment=server.get("environment"),
        owner=server.get("owner"),
        tags=server.get("tags", []),
        notes=server.get("notes"),
        enabled=server.get("enabled", True),
        database_count=database_count,
        created_at=server["created_at"],
        updated_at=server["updated_at"],
    )


async def list_servers(database):
    cursor = database.servers.find().sort(
        "name",
        1,
    )

    servers = await cursor.to_list(None)

    return [
        await server_to_response(
            database,
            server,
        )
        for server in servers
    ]


async def get_server(
    database,
    server_id: str,
):
    object_id = parse_server_id(server_id)

    server = await database.servers.find_one(
        {"_id": object_id}
    )

    if server is None:
        raise AppError(
            "Server not found.",
            code="SERVER_NOT_FOUND",
            status_code=404,
        )

    return server


async def create_server(
    database,
    data: ServerCreate,
):
    now = datetime.now(timezone.utc)

    document = data.model_dump(mode="json")

    document.update(
        {
            "name_key":
                normalize_server_name(data.name),
            "created_at": now,
            "updated_at": now,
        }
    )

    try:
        result = await database.servers.insert_one(
            document
        )
    except DuplicateKeyError:
        raise AppError(
            "A server with this name already exists.",
            code="SERVER_NAME_EXISTS",
            status_code=409,
        )

    server = await database.servers.find_one(
        {"_id": result.inserted_id}
    )

    return await server_to_response(
        database,
        server,
    )


async def update_server(
    database,
    server_id: str,
    data: ServerUpdate,
):
    object_id = parse_server_id(server_id)

    document = data.model_dump(mode="json")

    document["name_key"] = normalize_server_name(
        data.name
    )

    document["updated_at"] = datetime.now(
        timezone.utc
    )

    try:
        result = await database.servers.update_one(
            {"_id": object_id},
            {"$set": document},
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

    server = await database.servers.find_one(
        {"_id": object_id}
    )

    return await server_to_response(
        database,
        server,
    )


async def delete_server(
    database,
    server_id: str,
):
    object_id = parse_server_id(server_id)

    result = await database.servers.delete_one(
        {"_id": object_id}
    )

    if result.deleted_count == 0:
        raise AppError(
            "Server not found.",
            code="SERVER_NOT_FOUND",
            status_code=404,
        )

    # Remove the relationship from every DB connection.
    await database.database_connections.update_many(
        {
            "server_ids": server_id,
        },
        {
            "$pull": {
                "server_ids": server_id,
            }
        },
    )


async def list_server_databases(
    database,
    server_id: str,
):
    await get_server(
        database,
        server_id,
    )

    cursor = database.database_connections.find(
        {
            "server_ids": server_id,
        }
    ).sort("name", 1)

    return await cursor.to_list(None)