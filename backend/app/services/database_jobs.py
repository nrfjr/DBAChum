from app.connectors.mysql_jobs import get_mysql_jobs, mysql_job_operation
from app.connectors.oracle_jobs import get_oracle_jobs, oracle_job_operation
from app.connectors.sqlserver_jobs import get_sqlserver_jobs, sqlserver_job_operation
from app.core.exceptions import AppError
from app.schemas.database_action import DatabaseActionRisk
from app.schemas.user import UserResponse
from app.services.database_connections import get_database_connection
from app.services.database_operations import _run_audited


async def load_database_jobs(database, connection_id: str) -> dict:
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]
    if engine == "oracle":
        result = await get_oracle_jobs(connection)
    elif engine == "sqlserver":
        result = await get_sqlserver_jobs(connection)
    elif engine == "mysql":
        result = await get_mysql_jobs(connection)
    else:
        raise AppError("Jobs are unavailable for this engine.", status_code=400)
    return {"connection_id": connection_id, "engine": engine, **result}


async def operate_database_job(database, connection_id: str, data, operator: UserResponse):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]
    if engine == "oracle":
        runner = lambda conn: oracle_job_operation(conn, data)
    elif engine == "sqlserver":
        runner = lambda conn: sqlserver_job_operation(conn, data)
    elif engine == "mysql":
        runner = lambda conn: mysql_job_operation(conn, data)
    else:
        raise AppError("Job operations are unavailable for this engine.", status_code=400)

    return await _run_audited(
        database,
        connection_id=connection_id,
        operator=operator,
        action=f"job.{data.action.value}",
        target=data.job_id,
        risk=DatabaseActionRisk.DANGEROUS if data.action.value == "run" else DatabaseActionRisk.SENSITIVE,
        request_reference=data.request_reference,
        runner=runner,
    )
