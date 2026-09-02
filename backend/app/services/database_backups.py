from app.connectors.mysql_backups import get_mysql_backups
from app.connectors.oracle_backups import get_oracle_backups
from app.connectors.sqlserver_backups import get_sqlserver_backups
from app.core.exceptions import AppError
from app.services.database_connections import get_database_connection


async def load_database_backups(database, connection_id: str) -> dict:
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]

    if engine == "oracle":
        result = await get_oracle_backups(connection)
    elif engine == "sqlserver":
        result = await get_sqlserver_backups(connection)
    elif engine == "mysql":
        result = await get_mysql_backups(connection)
    else:
        raise AppError(
            f"Backup monitoring is not available for {engine}.",
            code="BACKUP_MONITORING_NOT_AVAILABLE",
            status_code=400,
        )

    return {
        "connection_id": connection_id,
        "engine": engine,
        **result,
    }
