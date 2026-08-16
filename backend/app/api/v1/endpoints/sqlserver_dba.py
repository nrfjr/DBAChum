from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.schemas.sqlserver_dba import (
    SqlServerActivityResponse,
    SqlServerSessionsResponse,
    SqlServerStorageResponse,
)
from app.schemas.user import UserResponse
from app.services.sqlserver_dba import (
    load_sqlserver_activity,
    load_sqlserver_sessions,
    load_sqlserver_storage,
)


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
    current_user: UserResponse = Depends(
        get_current_user
    ),
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
    current_user: UserResponse = Depends(
        get_current_user
    ),
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
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    return await load_sqlserver_activity(
        request.app.state.database,
        connection_id,
    )