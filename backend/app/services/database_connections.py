from datetime import datetime, timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppError
from app.core.security import encrypt_secret
from app.schemas.database_connection import (
    DatabaseConnectionCreate,
    DatabaseConnectionResponse,
    DatabaseConnectionUpdate,
)

from app.connectors.oracle import test_oracle_connection
from app.connectors.mysql import test_mysql_connection
from app.connectors.sqlserver import test_sqlserver_connection

def normalize_connection_name(name: str) -> str:
    return name.strip().lower()


def connection_is_active(connection: dict) -> bool:
    """Return whether DBAChum may use a connection for admin/manual work.

    Existing records predate the `active` field. Because the old checkbox was
    explicitly labelled "Monitor this connection", legacy records default to
    active even when their old `enabled` monitoring flag is false.
    """
    return bool(connection.get("active", True))


def connection_is_monitored(connection: dict) -> bool:
    """Return whether a connection belongs in monitoring/workspace flows."""
    if "monitor_enabled" in connection:
        return bool(connection.get("monitor_enabled"))
    return bool(connection.get("enabled", True))


def monitored_connections_filter() -> dict:
    """Mongo filter supporting both legacy and new connection documents."""
    return {
        "$and": [
            {
                "$or": [
                    {"active": True},
                    {"active": {"$exists": False}},
                ]
            },
            {
                "$or": [
                    {"monitor_enabled": True},
                    {
                        "monitor_enabled": {"$exists": False},
                        "enabled": True,
                    },
                ]
            },
        ]
    }


async def ensure_connection_flags_migrated(database) -> None:
    """Backfill the split connection flags without changing old intent.

    The historic `enabled` field represented monitoring. Therefore old rows
    become active=True and monitor_enabled=<old enabled>. The legacy field is
    retained as a mirror so rollback to an older build remains predictable.
    """
    await database.database_connections.update_many(
        {
            "$or": [
                {"active": {"$exists": False}},
                {"monitor_enabled": {"$exists": False}},
            ]
        },
        [
            {
                "$set": {
                    "active": {"$ifNull": ["$active", True]},
                    "monitor_enabled": {
                        "$ifNull": [
                            "$monitor_enabled",
                            {"$ifNull": ["$enabled", True]},
                        ]
                    },
                }
            },
            {
                "$set": {
                    "enabled": "$monitor_enabled",
                }
            },
        ],
    )


def parse_connection_id(connection_id: str) -> ObjectId:
    try:
        return ObjectId(connection_id)
    except Exception:
        raise AppError(
            "Database connection not found.",
            code="CONNECTION_NOT_FOUND",
            status_code=404,
        )


def connection_to_response(connection: dict) -> DatabaseConnectionResponse:
    return DatabaseConnectionResponse(
        id=str(connection["_id"]),
        name=connection["name"],
        engine=connection["engine"],
        host=connection["host"],
        port=connection["port"],
        username=connection["username"],
        database=connection.get("database"),
        oracle_identifier_type=connection.get("oracle_identifier_type"),
        oracle_identifier=connection.get("oracle_identifier"),
        oracle_auth_mode=(
            connection.get("oracle_auth_mode", "normal")
            if connection["engine"] == "oracle"
            else None
        ),
        sqlserver_provider=(
            connection.get("sqlserver_provider", "auto")
            if connection["engine"] == "sqlserver"
            else None
        ),
        sqlserver_driver=(
            connection.get("sqlserver_driver")
            if connection["engine"] == "sqlserver"
            else None
        ),
        sqlserver_encrypt=(
            connection.get("sqlserver_encrypt", "auto")
            if connection["engine"] == "sqlserver"
            else None
        ),
        active=connection_is_active(connection),
        monitor_enabled=connection_is_monitored(connection),
        enabled=connection_is_monitored(connection),
        has_password=bool(connection.get("password_encrypted")),
        created_at=connection["created_at"],
        updated_at=connection["updated_at"],
        server_ids=connection.get("server_ids",[],),
    )


async def list_database_connections(database):
    await ensure_connection_flags_migrated(database)
    cursor = database.database_connections.find().sort("name", 1)
    connections = await cursor.to_list(None)

    return [
        connection_to_response(connection)
        for connection in connections
    ]


async def get_database_connection(database, connection_id: str):
    object_id = parse_connection_id(connection_id)

    connection = await database.database_connections.find_one(
        {"_id": object_id}
    )

    if connection is None:
        raise AppError(
            "Database connection not found.",
            code="CONNECTION_NOT_FOUND",
            status_code=404,
        )

    return connection


async def create_database_connection(
    database,
    data: DatabaseConnectionCreate,
):
    now = datetime.now(timezone.utc)

    document = data.model_dump(mode="json")

    password = document.pop("password")

    document.update(
        {
            "name_key": normalize_connection_name(data.name),
            "password_encrypted": encrypt_secret(password),
            "created_at": now,
            "updated_at": now,
        }
    )

    try:
        await validate_server_ids(database,data.server_ids,)
        result = await database.database_connections.insert_one(document)
    except DuplicateKeyError:
        raise AppError(
            "A database connection with this name already exists.",
            code="CONNECTION_NAME_EXISTS",
            status_code=409,
        )

    created = await database.database_connections.find_one(
        {"_id": result.inserted_id}
    )

    return connection_to_response(created)


async def update_database_connection(
    database,
    connection_id: str,
    data: DatabaseConnectionUpdate,
):
    object_id = parse_connection_id(connection_id)

    existing = await database.database_connections.find_one(
        {"_id": object_id}
    )

    if existing is None:
        raise AppError(
            "Database connection not found.",
            code="CONNECTION_NOT_FOUND",
            status_code=404,
        )

    document = data.model_dump(mode="json")
    password = document.pop("password", None)

    if (
        data.username != existing.get("username")
        and not password
    ):
        raise AppError(
            "Password is required when changing the connection username.",
            code="CONNECTION_PASSWORD_REQUIRED",
            status_code=400,
        )

    document["name_key"] = normalize_connection_name(data.name)
    document["updated_at"] = datetime.now(timezone.utc)

    if password:
        document["password_encrypted"] = encrypt_secret(password)

    try:
        await validate_server_ids(database,data.server_ids,)
        result = await database.database_connections.update_one(
            {"_id": object_id},
            {"$set": document},
        )
    except DuplicateKeyError:
        raise AppError(
            "A database connection with this name already exists.",
            code="CONNECTION_NAME_EXISTS",
            status_code=409,
        )

    if result.matched_count == 0:
        raise AppError(
            "Database connection not found.",
            code="CONNECTION_NOT_FOUND",
            status_code=404,
        )

    updated = await database.database_connections.find_one(
        {"_id": object_id}
    )

    return connection_to_response(updated)


async def delete_database_connection(
    database,
    connection_id: str,
) -> None:
    object_id = parse_connection_id(connection_id)

    dependent_profile = await database.provisioning_profiles.find_one(
        {
            "$or": [
                {"schema_connection_id": connection_id},
                {"table_steps.connection_id": connection_id},
            ]
        },
        {"name": 1},
    )

    if dependent_profile is not None:
        raise AppError(
            "This connection is used by provisioning profile "
            f'"{dependent_profile.get("name", "Unnamed profile")}". '
            "Reassign or remove that profile dependency first.",
            code="CONNECTION_IN_USE_BY_PROVISIONING",
            status_code=409,
        )

    result = await database.database_connections.delete_one(
        {"_id": object_id}
    )

    if result.deleted_count == 0:
        raise AppError(
            "Database connection not found.",
            code="CONNECTION_NOT_FOUND",
            status_code=404,
        )

async def test_database_connection(
    database,
    connection_id: str,
):
    connection = await get_database_connection(
        database,
        connection_id,
    )

    engine = connection["engine"]

    if engine == "oracle":
        result = await test_oracle_connection(connection)

        return {
            "success": True,
            "engine": "oracle",
            "message": "Oracle connection successful.",
            **result,
        }

    if engine == "sqlserver":
        result = await test_sqlserver_connection(connection)

        return {
            "success": True,
            "engine": "sqlserver",
            "message": "SQL Server connection successful.",
            **result,
        }

    if engine == "mysql":
        result = await test_mysql_connection(connection)

        return {
            "success": True,
            "engine": "mysql",
            "message": "MySQL connection successful.",
            **result,
        }

    raise AppError(
        f"The {engine} connector is not supported.",
        code="CONNECTOR_NOT_SUPPORTED",
        status_code=400,
    )

async def validate_server_ids(
    database,
    server_ids: list[str],
) -> None:
    if not server_ids:
        return

    unique_ids = list(dict.fromkeys(server_ids))

    if len(unique_ids) != len(server_ids):
        raise AppError(
            "Duplicate server relationships are not allowed.",
            code="DUPLICATE_SERVER_RELATIONSHIP",
            status_code=400,
        )

    object_ids = []

    for server_id in unique_ids:
        try:
            object_ids.append(
                ObjectId(server_id)
            )
        except Exception:
            raise AppError(
                "One or more selected servers are invalid.",
                code="INVALID_SERVER_RELATIONSHIP",
                status_code=400,
            )

    count = await database.servers.count_documents(
        {
            "_id": {
                "$in": object_ids,
            }
        }
    )

    if count != len(object_ids):
        raise AppError(
            "One or more selected servers do not exist.",
            code="SERVER_RELATIONSHIP_NOT_FOUND",
            status_code=400,
        )