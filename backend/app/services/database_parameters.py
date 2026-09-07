from app.connectors.mysql_parameters import get_mysql_parameters
from app.connectors.oracle_parameters import get_oracle_parameters
from app.connectors.sqlserver_parameters import get_sqlserver_parameters
from app.core.exceptions import AppError
from app.services.database_connections import get_database_connection


async def load_database_parameters(database, connection_id: str) -> dict:
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]

    if engine == "oracle":
        result = await get_oracle_parameters(connection)
    elif engine == "sqlserver":
        result = await get_sqlserver_parameters(connection)
    elif engine == "mysql":
        result = await get_mysql_parameters(connection)
    else:
        raise AppError(
            "Parameter inspection is unavailable for this engine.",
            code="DATABASE_PARAMETERS_UNAVAILABLE",
            status_code=400,
        )

    return {
        "connection_id": connection_id,
        "engine": engine,
        **result,
    }
