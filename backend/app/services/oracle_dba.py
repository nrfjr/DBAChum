from app.connectors.oracle_activity import (
    get_oracle_activity,
)
from app.connectors.oracle_sessions import (
    get_oracle_sessions,
)
from app.connectors.oracle_storage import (
    get_oracle_storage,
)
from app.core.exceptions import AppError
from app.services.database_connections import (
    get_database_connection,
)


async def get_oracle_target(
    database,
    connection_id: str,
):
    connection = await get_database_connection(
        database,
        connection_id,
    )

    if connection["engine"] != "oracle":
        raise AppError(
            "This utility is only available "
            "for Oracle connections.",
            code="ORACLE_UTILITY_NOT_AVAILABLE",
            status_code=400,
        )

    if not connection.get("enabled", True):
        raise AppError(
            "Monitoring is disabled for "
            "this connection.",
            code="CONNECTION_DISABLED",
            status_code=400,
        )

    return connection


async def load_oracle_sessions(
    database,
    connection_id: str,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    return await get_oracle_sessions(
        connection
    )


async def load_oracle_storage(
    database,
    connection_id: str,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    return await get_oracle_storage(
        connection
    )


async def load_oracle_activity(
    database,
    connection_id: str,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    return await get_oracle_activity(
        connection
    )