from datetime import datetime, timezone

from bson import ObjectId
from cryptography.fernet import InvalidToken
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppError
from app.core.security import decrypt_secret, encrypt_secret
from app.schemas.record import RecordCreate, RecordResponse, RecordUpdate


def _parse_object_id(value: str, *, field_name: str) -> ObjectId:
    try:
        return ObjectId(value)
    except Exception:
        raise AppError(
            f"Linked {field_name} was not found.",
            code=f"RECORD_{field_name.upper()}_NOT_FOUND",
            status_code=404,
        )


def parse_record_id(record_id: str) -> ObjectId:
    try:
        return ObjectId(record_id)
    except Exception:
        raise AppError(
            "Record not found.",
            code="RECORD_NOT_FOUND",
            status_code=404,
        )


def normalize_identity(name: str, environment: str | None) -> str:
    return f"{name.strip().lower()}|{(environment or '').strip().lower()}"


async def _validate_relationships(
    database,
    *,
    connection_id: str | None,
    server_id: str | None,
) -> None:
    if connection_id:
        connection_object_id = _parse_object_id(
            connection_id,
            field_name="connection",
        )
        connection = await database.database_connections.find_one(
            {"_id": connection_object_id},
            {"_id": 1},
        )
        if connection is None:
            raise AppError(
                "Linked database connection was not found.",
                code="RECORD_CONNECTION_NOT_FOUND",
                status_code=404,
            )

    if server_id:
        server_object_id = _parse_object_id(
            server_id,
            field_name="server",
        )
        server = await database.servers.find_one(
            {"_id": server_object_id},
            {"_id": 1},
        )
        if server is None:
            raise AppError(
                "Linked server was not found.",
                code="RECORD_SERVER_NOT_FOUND",
                status_code=404,
            )


async def record_to_response(database, document: dict) -> RecordResponse:
    connection_name = None
    connection_id = document.get("connection_id")
    if connection_id:
        try:
            connection = await database.database_connections.find_one(
                {"_id": ObjectId(connection_id)},
                {"name": 1},
            )
        except Exception:
            connection = None
        if connection:
            connection_name = connection.get("name")

    server_name = None
    server_id = document.get("server_id")
    if server_id:
        try:
            server = await database.servers.find_one(
                {"_id": ObjectId(server_id)},
                {"name": 1},
            )
        except Exception:
            server = None
        if server:
            server_name = server.get("name")

    return RecordResponse(
        id=str(document["_id"]),
        name=document["name"],
        record_type=document.get("record_type", "database"),
        status=document.get("status", "active"),
        engine=document.get("engine"),
        hostname=document.get("hostname"),
        ip_address=document.get("ip_address"),
        port=document.get("port"),
        environment=document.get("environment"),
        version=document.get("version"),
        username=document.get("username"),
        application=document.get("application"),
        owner=document.get("owner"),
        url=document.get("url"),
        notes=document.get("notes"),
        tags=document.get("tags", []),
        custom_fields=document.get("custom_fields", []),
        connection_id=connection_id,
        server_id=server_id,
        has_password=bool(document.get("password_encrypted")),
        connection_name=connection_name,
        server_name=server_name,
        created_by=document.get("created_by"),
        updated_by=document.get("updated_by"),
        created_at=document["created_at"],
        updated_at=document["updated_at"],
    )


async def list_records(database) -> list[RecordResponse]:
    documents = await database.records.find().sort("name", 1).to_list(None)
    return [await record_to_response(database, item) for item in documents]


async def get_record(database, record_id: str) -> dict:
    object_id = parse_record_id(record_id)
    document = await database.records.find_one({"_id": object_id})
    if document is None:
        raise AppError(
            "Record not found.",
            code="RECORD_NOT_FOUND",
            status_code=404,
        )
    return document


async def get_record_response(database, record_id: str) -> RecordResponse:
    return await record_to_response(database, await get_record(database, record_id))


async def create_record(
    database,
    data: RecordCreate,
    *,
    created_by: str,
) -> RecordResponse:
    await _validate_relationships(
        database,
        connection_id=data.connection_id,
        server_id=data.server_id,
    )

    now = datetime.now(timezone.utc)
    document = data.model_dump(mode="json")
    password = document.pop("password", None)
    document.update(
        {
            "identity_key": normalize_identity(data.name, data.environment),
            "created_by": created_by,
            "updated_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
    )
    if password:
        document["password_encrypted"] = encrypt_secret(password)

    try:
        result = await database.records.insert_one(document)
    except DuplicateKeyError:
        raise AppError(
            "A record with this name and environment already exists.",
            code="RECORD_IDENTITY_EXISTS",
            status_code=409,
        )

    created = await database.records.find_one({"_id": result.inserted_id})
    return await record_to_response(database, created)


async def update_record(
    database,
    record_id: str,
    data: RecordUpdate,
    *,
    updated_by: str,
) -> RecordResponse:
    object_id = parse_record_id(record_id)
    existing = await get_record(database, record_id)

    await _validate_relationships(
        database,
        connection_id=data.connection_id,
        server_id=data.server_id,
    )

    document = data.model_dump(mode="json")
    password = document.pop("password", None)
    document.update(
        {
            "identity_key": normalize_identity(data.name, data.environment),
            "updated_by": updated_by,
            "updated_at": datetime.now(timezone.utc),
        }
    )

    update_document: dict = {"$set": document}
    if password:
        document["password_encrypted"] = encrypt_secret(password)
    elif "password_encrypted" not in existing:
        update_document["$unset"] = {"password_encrypted": ""}

    try:
        result = await database.records.update_one(
            {"_id": object_id},
            update_document,
        )
    except DuplicateKeyError:
        raise AppError(
            "A record with this name and environment already exists.",
            code="RECORD_IDENTITY_EXISTS",
            status_code=409,
        )

    if result.matched_count == 0:
        raise AppError(
            "Record not found.",
            code="RECORD_NOT_FOUND",
            status_code=404,
        )

    updated = await database.records.find_one({"_id": object_id})
    return await record_to_response(database, updated)


async def delete_record(database, record_id: str) -> None:
    object_id = parse_record_id(record_id)
    result = await database.records.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise AppError(
            "Record not found.",
            code="RECORD_NOT_FOUND",
            status_code=404,
        )


async def reveal_record_password(database, record_id: str) -> str:
    document = await get_record(database, record_id)
    encrypted = document.get("password_encrypted")
    if not encrypted:
        raise AppError(
            "This record does not have a stored password.",
            code="RECORD_PASSWORD_NOT_SET",
            status_code=404,
        )

    try:
        return decrypt_secret(encrypted)
    except (InvalidToken, ValueError):
        raise AppError(
            "The stored record password could not be decrypted with the current encryption key.",
            code="RECORD_PASSWORD_DECRYPT_FAILED",
            status_code=500,
        )
