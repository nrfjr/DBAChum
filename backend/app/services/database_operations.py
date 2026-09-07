from typing import Awaitable, Callable

from app.connectors.mysql_operations import (
    mysql_access_operation,
    mysql_account_operation,
    mysql_session_operation,
    mysql_storage_operation,
)
from app.connectors.oracle_operations import (
    oracle_session_operation,
    oracle_storage_operation,
)
from app.connectors.sqlserver_operations import (
    sqlserver_access_operation,
    sqlserver_account_operation,
    sqlserver_session_operation,
    sqlserver_storage_operation,
)
from app.core.exceptions import AppError
from app.schemas.database_action import DatabaseActionRisk, DatabaseActionStatus
from app.schemas.user import UserResponse
from app.services.database_actions import finish_database_action, start_database_action
from app.services.database_connections import get_database_connection


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

    # Never persist plaintext reset passwords. Statements that may contain a
    # password are reduced to an operation marker before entering the audit log.
    details = {
        key: value
        for key, value in result.items()
        if key not in {"before", "after", "statement"}
    }
    if result.get("statement"):
        details["statement_executed"] = True

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
