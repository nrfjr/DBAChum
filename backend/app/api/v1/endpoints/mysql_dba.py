from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.schemas.mysql_dba import (
    MySqlActivityResponse,
    MySqlSessionsResponse,
    MySqlStorageResponse,
)
from app.schemas.user import UserResponse
from app.services.mysql_dba import (
    load_mysql_activity,
    load_mysql_sessions,
    load_mysql_storage,
)
from app.core.permissions import Permission
from app.dependencies.permissions import require_permission


router = APIRouter(
    prefix="/databases",
    tags=["MySQL DBA"],
)


@router.get(
    "/{connection_id}/mysql/sessions",
    response_model=MySqlSessionsResponse,
)
async def sessions(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_mysql_sessions(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}/mysql/storage",
    response_model=MySqlStorageResponse,
)
async def storage(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_mysql_storage(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}/mysql/activity",
    response_model=MySqlActivityResponse,
)
async def activity(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_mysql_activity(
        request.app.state.database,
        connection_id,
    )