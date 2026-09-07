from app.connectors.mysql_performance import get_mysql_sql_plan, get_mysql_top_sql
from app.connectors.oracle_performance import get_oracle_sql_plan, get_oracle_top_sql
from app.connectors.sqlserver_performance import get_sqlserver_sql_plan, get_sqlserver_top_sql
from app.core.exceptions import AppError
from app.services.database_connections import get_database_connection


async def load_top_sql(database, connection_id: str, *, limit: int = 20) -> dict:
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]
    safe_limit = max(1, min(int(limit), 100))

    if engine == "oracle":
        result = await get_oracle_top_sql(connection, safe_limit)
    elif engine == "sqlserver":
        result = await get_sqlserver_top_sql(connection, safe_limit)
    elif engine == "mysql":
        result = await get_mysql_top_sql(connection, safe_limit)
    else:
        raise AppError(
            "Top SQL is unavailable for this engine.",
            code="TOP_SQL_UNAVAILABLE",
            status_code=400,
        )

    return {"connection_id": connection_id, "engine": engine, **result}


async def load_sql_plan(database, connection_id: str, data) -> dict:
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]

    if engine == "oracle":
        result = await get_oracle_sql_plan(connection, data)
    elif engine == "sqlserver":
        result = await get_sqlserver_sql_plan(connection, data)
    elif engine == "mysql":
        result = await get_mysql_sql_plan(connection, data)
    else:
        raise AppError(
            "SQL plan inspection is unavailable for this engine.",
            code="SQL_PLAN_UNAVAILABLE",
            status_code=400,
        )

    return {"connection_id": connection_id, "engine": engine, **result}
