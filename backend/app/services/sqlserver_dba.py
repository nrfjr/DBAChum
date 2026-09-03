from app.connectors.sqlserver_activity import (
    get_sqlserver_activity,
)
from app.connectors.sqlserver_sessions import (
    get_sqlserver_sessions,
)
from app.connectors.sqlserver_storage import (
    get_sqlserver_storage,
)
from app.connectors.sqlserver_security import (
    get_sqlserver_security,
)
from app.connectors.sqlserver_health import (
    get_sqlserver_health,
)
from app.core.exceptions import AppError
from app.services.database_connections import (
    get_database_connection,
)


async def get_sqlserver_target(
    database,
    connection_id: str,
):
    connection = await get_database_connection(
        database,
        connection_id,
    )

    if connection["engine"] != "sqlserver":
        raise AppError(
            "This utility is only available "
            "for SQL Server connections.",
            code="SQLSERVER_UTILITY_NOT_AVAILABLE",
            status_code=400,
        )

    return connection


async def load_sqlserver_sessions(
    database,
    connection_id: str,
):
    return await get_sqlserver_sessions(
        await get_sqlserver_target(
            database,
            connection_id,
        )
    )


async def load_sqlserver_storage(
    database,
    connection_id: str,
):
    return await get_sqlserver_storage(
        await get_sqlserver_target(
            database,
            connection_id,
        )
    )


async def load_sqlserver_activity(
    database,
    connection_id: str,
):
    return await get_sqlserver_activity(
        await get_sqlserver_target(
            database,
            connection_id,
        )
    )

async def load_sqlserver_security(
    database,
    connection_id: str,
):
    return await get_sqlserver_security(
        await get_sqlserver_target(
            database,
            connection_id,
        )
    )


async def load_sqlserver_health(
    database,
    connection_id: str,
):
    return await get_sqlserver_health(
        await get_sqlserver_target(
            database,
            connection_id,
        )
    )
