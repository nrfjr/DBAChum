from app.connectors.mysql_activity import (
    get_mysql_activity,
)
from app.connectors.mysql_health import (
    get_mysql_health,
)
from app.connectors.mysql_sessions import (
    get_mysql_sessions,
)
from app.connectors.mysql_storage import (
    get_mysql_storage,
)
from app.core.exceptions import AppError
from app.services.database_connections import (
    get_database_connection,
)


async def get_mysql_target(
    database,
    connection_id: str,
):
    connection = await get_database_connection(
        database,
        connection_id,
    )

    if connection["engine"] != "mysql":
        raise AppError(
            "This utility is only available "
            "for MySQL connections.",
            code="MYSQL_UTILITY_NOT_AVAILABLE",
            status_code=400,
        )

    return connection


async def load_mysql_sessions(
    database,
    connection_id: str,
):
    return await get_mysql_sessions(
        await get_mysql_target(
            database,
            connection_id,
        )
    )


async def load_mysql_storage(
    database,
    connection_id: str,
):
    return await get_mysql_storage(
        await get_mysql_target(
            database,
            connection_id,
        )
    )


async def load_mysql_activity(
    database,
    connection_id: str,
):
    return await get_mysql_activity(
        await get_mysql_target(
            database,
            connection_id,
        )
    )

async def load_mysql_health(
    database,
    connection_id: str,
):
    return await get_mysql_health(
        await get_mysql_target(
            database,
            connection_id,
        )
    )
