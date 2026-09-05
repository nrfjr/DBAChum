from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.schemas.sqlserver_dba import (
    SqlServerActivityResponse,
    SqlServerSessionsResponse,
    SqlServerStorageResponse,
    SqlServerSecurityResponse,
    SqlServerHealthResponse,
)
from app.schemas.user import UserResponse
from app.services.sqlserver_dba import (
    load_sqlserver_activity,
    load_sqlserver_sessions,
    load_sqlserver_storage,
    load_sqlserver_security,
    load_sqlserver_health,
)
from app.core.permissions import Permission
from app.dependencies.permissions import require_permission


router = APIRouter(
    prefix="/databases",
    tags=["SQL Server DBA"],
)


@router.get(
    "/{connection_id}/sqlserver/sessions",
    response_model=SqlServerSessionsResponse,
)
async def sessions(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_sqlserver_sessions(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}/sqlserver/storage",
    response_model=SqlServerStorageResponse,
)
async def storage(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_sqlserver_storage(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}/sqlserver/activity",
    response_model=SqlServerActivityResponse,
)
async def activity(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_sqlserver_activity(
        request.app.state.database,
        connection_id,
    )
    

@router.get(
    "/{connection_id}/sqlserver/security",
    response_model=SqlServerSecurityResponse,
)
async def security(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DATABASE_INSPECT)),
):
    return await load_sqlserver_security(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}/sqlserver/health",
    response_model=SqlServerHealthResponse,
)
async def health(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_sqlserver_health(
        request.app.state.database,
        connection_id,
    )
