from fastapi import APIRouter, Depends, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.database_action import DatabaseActionAuditResponse
from app.schemas.database_operation import (
    AccessOperationRequest,
    AccountOperationRequest,
    BackupOperationRequest,
    MaintenanceOperationRequest,
    ParameterOperationRequest,
    SessionOperationRequest,
    StorageOperationRequest,
)
from app.schemas.user import UserResponse
from app.services.database_operations import (
    operate_access,
    operate_account,
    operate_backup,
    operate_maintenance,
    operate_parameter,
    operate_session,
    operate_storage,
)


router = APIRouter(prefix="/databases", tags=["Database Operations"])


@router.post(
    "/{connection_id}/operations/session",
    response_model=DatabaseActionAuditResponse,
)
async def session_operation(
    connection_id: str,
    data: SessionOperationRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await operate_session(request.app.state.database, connection_id, data, current_user)


@router.post(
    "/{connection_id}/operations/storage",
    response_model=DatabaseActionAuditResponse,
)
async def storage_operation(
    connection_id: str,
    data: StorageOperationRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await operate_storage(request.app.state.database, connection_id, data, current_user)


@router.post(
    "/{connection_id}/operations/account",
    response_model=DatabaseActionAuditResponse,
)
async def account_operation(
    connection_id: str,
    data: AccountOperationRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await operate_account(request.app.state.database, connection_id, data, current_user)


@router.post(
    "/{connection_id}/operations/access",
    response_model=DatabaseActionAuditResponse,
)
async def access_operation(
    connection_id: str,
    data: AccessOperationRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await operate_access(request.app.state.database, connection_id, data, current_user)


@router.post(
    "/{connection_id}/operations/parameter",
    response_model=DatabaseActionAuditResponse,
)
async def parameter_operation(
    connection_id: str,
    data: ParameterOperationRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await operate_parameter(request.app.state.database, connection_id, data, current_user)


@router.post(
    "/{connection_id}/operations/maintenance",
    response_model=DatabaseActionAuditResponse,
)
async def maintenance_operation(
    connection_id: str,
    data: MaintenanceOperationRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await operate_maintenance(request.app.state.database, connection_id, data, current_user)


@router.post(
    "/{connection_id}/operations/backup",
    response_model=DatabaseActionAuditResponse,
)
async def backup_operation(
    connection_id: str,
    data: BackupOperationRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await operate_backup(request.app.state.database, connection_id, data, current_user)
