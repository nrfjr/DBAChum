import asyncio

from bson import ObjectId

from typing import Awaitable, Callable

from app.connectors.mysql_backup_operations import mysql_backup_operation
from app.connectors.database_maintenance import (
    mysql_database_maintenance,
    oracle_database_maintenance,
    sqlserver_database_maintenance,
)
from app.connectors.mysql_parameters import mysql_parameter_operation
from app.connectors.mysql_operations import (
    mysql_access_operation,
    mysql_account_operation,
    mysql_session_operation,
    mysql_storage_operation,
)
from app.connectors.oracle_maintenance import oracle_rman_backup, oracle_rman_maintenance
from app.connectors.oracle_parameters import oracle_parameter_operation
from app.connectors.oracle_operations import (
    oracle_session_operation,
    oracle_storage_operation,
)
from app.connectors.sqlserver_backup_operations import sqlserver_backup_operation
from app.connectors.sqlserver_parameters import sqlserver_parameter_operation
from app.connectors.sqlserver_operations import (
    sqlserver_access_operation,
    sqlserver_account_operation,
    sqlserver_session_operation,
    sqlserver_storage_operation,
)
from app.core.exceptions import AppError
from app.schemas.database_action import DatabaseActionRisk, DatabaseActionStatus
from app.schemas.user import UserResponse
from app.services.database_actions import (
    database_action_to_response,
    finish_database_action,
    start_database_action,
)
from app.services.database_connections import get_database_connection


_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _audit_details(result: dict) -> dict:
    details = {
        key: value
        for key, value in result.items()
        if key not in {"before", "after", "statement"}
    }
    if result.get("statement"):
        details["statement_executed"] = True
    return details


def _track_task(task: asyncio.Task) -> None:
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)



async def _run_audited(
    database,
    *,
    connection_id: str,
    operator: UserResponse,
    action: str,
    target: str | None,
    risk: DatabaseActionRisk,
    request_reference: str | None,
    runner: Callable[[dict], Awaitable[dict]],
):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]
    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine=engine,
        action=action,
        operator=operator,
        target=target,
        risk=risk,
        request_reference=request_reference,
    )

    try:
        result = await runner(connection)
    except AppError as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            error=exc.message,
            details={"error_code": exc.code},
        )
        raise
    except Exception as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            error=str(exc),
        )
        raise

    # Never persist plaintext reset passwords or full executable statements.
    # Action-specific results are reduced to safe structured details.
    details = _audit_details(result)

    return await finish_database_action(
        database,
        audit_id,
        status=DatabaseActionStatus.SUCCEEDED,
        before=result.get("before"),
        after=result.get("after"),
        details=details,
    )


async def operate_session(database, connection_id: str, data, operator: UserResponse):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]

    if engine == "oracle":
        runner = lambda conn: oracle_session_operation(conn, data)
        target = (
            f"{data.session_id},{data.serial_number}"
            if data.serial_number is not None
            else str(data.session_id)
        )
    elif engine == "sqlserver":
        runner = lambda conn: sqlserver_session_operation(conn, data)
        target = str(data.session_id)
    elif engine == "mysql":
        runner = lambda conn: mysql_session_operation(conn, data)
        target = str(data.session_id)
    else:
        raise AppError("Session operations are unavailable for this engine.", status_code=400)

    return await _run_audited(
        database,
        connection_id=connection_id,
        operator=operator,
        action=f"session.{data.action.value}",
        target=target,
        risk=DatabaseActionRisk.DANGEROUS,
        request_reference=data.request_reference,
        runner=runner,
    )


async def operate_storage(database, connection_id: str, data, operator: UserResponse):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]

    if engine == "oracle":
        runner = lambda conn: oracle_storage_operation(conn, data)
    elif engine == "sqlserver":
        runner = lambda conn: sqlserver_storage_operation(conn, data)
    elif engine == "mysql":
        runner = lambda conn: mysql_storage_operation(conn, data)
    else:
        raise AppError("Storage operations are unavailable for this engine.", status_code=400)

    target = data.file_name or data.logical_name or data.physical_name or data.tablespace_name
    return await _run_audited(
        database,
        connection_id=connection_id,
        operator=operator,
        action=f"storage.{data.action.value}",
        target=target,
        risk=DatabaseActionRisk.DANGEROUS,
        request_reference=data.request_reference,
        runner=runner,
    )


async def operate_account(database, connection_id: str, data, operator: UserResponse):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]

    if engine == "oracle":
        raise AppError(
            "Oracle account lifecycle is already managed by the existing Oracle user actions.",
            code="ORACLE_ACCOUNT_USE_LIFECYCLE",
            status_code=400,
        )
    if engine == "sqlserver":
        runner = lambda conn: sqlserver_account_operation(conn, data)
    elif engine == "mysql":
        runner = lambda conn: mysql_account_operation(conn, data)
    else:
        raise AppError("Account operations are unavailable for this engine.", status_code=400)

    return await _run_audited(
        database,
        connection_id=connection_id,
        operator=operator,
        action=f"account.{data.action.value}",
        target=data.account_name if not data.host else f"{data.account_name}@{data.host}",
        risk=(
            DatabaseActionRisk.DANGEROUS
            if data.action.value == "disable"
            else DatabaseActionRisk.SENSITIVE
        ),
        request_reference=data.request_reference,
        runner=runner,
    )


async def operate_access(database, connection_id: str, data, operator: UserResponse):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]

    if engine == "oracle":
        raise AppError(
            "Oracle grants and roles are already managed by the Oracle access/role workspace.",
            code="ORACLE_ACCESS_USE_ROLE_WORKSPACE",
            status_code=400,
        )
    if engine == "sqlserver":
        runner = lambda conn: sqlserver_access_operation(conn, data)
    elif engine == "mysql":
        runner = lambda conn: mysql_access_operation(conn, data)
    else:
        raise AppError("Access operations are unavailable for this engine.", status_code=400)

    return await _run_audited(
        database,
        connection_id=connection_id,
        operator=operator,
        action=f"access.{data.action.value}",
        target=data.principal if not data.host else f"{data.principal}@{data.host}",
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=data.request_reference,
        runner=runner,
    )


async def operate_parameter(database, connection_id: str, data, operator: UserResponse):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]
    if engine == "oracle":
        runner = lambda conn: oracle_parameter_operation(conn, data)
    elif engine == "sqlserver":
        runner = lambda conn: sqlserver_parameter_operation(conn, data)
    elif engine == "mysql":
        runner = lambda conn: mysql_parameter_operation(conn, data)
    else:
        raise AppError("Parameter operations are unavailable for this engine.", status_code=400)

    return await _run_audited(
        database,
        connection_id=connection_id,
        operator=operator,
        action=f"parameter.{data.action.value}",
        target=data.name,
        risk=DatabaseActionRisk.DANGEROUS,
        request_reference=data.request_reference,
        runner=runner,
    )


async def _finish_background_operation(database, audit_id: str, runner):
    try:
        result = await runner()
    except AppError as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            error=exc.message,
            details={"error_code": exc.code},
        )
        return
    except asyncio.CancelledError:
        try:
            await finish_database_action(
                database,
                audit_id,
                status=DatabaseActionStatus.FAILED,
                error="Background database operation was cancelled because the DBAChum process stopped.",
            )
        finally:
            raise
    except Exception as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            error=str(exc),
        )
        return

    await finish_database_action(
        database,
        audit_id,
        status=DatabaseActionStatus.SUCCEEDED,
        before=result.get("before"),
        after=result.get("after"),
        details=_audit_details(result),
    )


async def _start_background_operation(
    database,
    *,
    connection: dict,
    connection_id: str,
    operator: UserResponse,
    action: str,
    target: str | None,
    risk: DatabaseActionRisk,
    request_reference: str | None,
    runner,
):
    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine=connection["engine"],
        action=action,
        operator=operator,
        target=target,
        risk=risk,
        request_reference=request_reference,
        details={"background": True},
    )
    task = asyncio.create_task(_finish_background_operation(database, audit_id, runner))
    _track_task(task)
    document = await database.database_action_audit.find_one({"_id": ObjectId(audit_id)})
    return database_action_to_response(document)


async def operate_maintenance(database, connection_id: str, data, operator: UserResponse):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]
    action = data.action.value

    if action in {"delete_archivelogs", "delete_obsolete"}:
        if engine != "oracle":
            raise AppError(
                "Archive/FRA cleanup is an Oracle RMAN operation.",
                code="MAINTENANCE_OPERATION_UNSUPPORTED",
                status_code=400,
            )
        target = (
            f"archivelogs older than {data.older_than_days} day(s)"
            if action == "delete_archivelogs"
            else "RMAN obsolete backups"
        )
        runner = lambda: oracle_rman_maintenance(database, connection, data)
    else:
        target = data.table_name or data.schema_name or connection.get("database") or connection.get("oracle_identifier") or connection.get("name")
        if engine == "oracle":
            runner = lambda: oracle_database_maintenance(connection, data)
        elif engine == "sqlserver":
            runner = lambda: sqlserver_database_maintenance(connection, data)
        elif engine == "mysql":
            runner = lambda: mysql_database_maintenance(connection, data)
        else:
            raise AppError("Database maintenance is unavailable for this engine.", status_code=400)

    return await _start_background_operation(
        database,
        connection=connection,
        connection_id=connection_id,
        operator=operator,
        action=f"maintenance.{action}",
        target=target,
        risk=DatabaseActionRisk.DANGEROUS,
        request_reference=data.request_reference,
        runner=runner,
    )


async def operate_backup(database, connection_id: str, data, operator: UserResponse):
    connection = await get_database_connection(database, connection_id)
    engine = connection["engine"]
    if engine == "oracle":
        runner = lambda: oracle_rman_backup(database, connection, data)
    elif engine == "sqlserver":
        runner = lambda: sqlserver_backup_operation(connection, data)
    elif engine == "mysql":
        if data.action.value != "full":
            raise AppError(
                "MySQL/MariaDB backup currently exposes a full logical mysqldump operation.",
                code="MYSQL_BACKUP_TYPE_UNSUPPORTED",
                status_code=400,
            )
        runner = lambda: mysql_backup_operation(database, connection, data)
    else:
        raise AppError("Backup execution is unavailable for this engine.", status_code=400)

    return await _start_background_operation(
        database,
        connection=connection,
        connection_id=connection_id,
        operator=operator,
        action=f"backup.{data.action.value}",
        target=connection.get("database") or connection.get("oracle_identifier") or connection.get("name"),
        risk=DatabaseActionRisk.DANGEROUS,
        request_reference=data.request_reference,
        runner=runner,
    )
