from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from app.schemas.oracle_dba import (
    OracleActivityResponse,
    OracleSessionsResponse,
    OracleStorageResponse,
    OracleDatabaseUsersResponse,
)
from app.schemas.user import UserResponse
from app.services.oracle_dba import (
    load_oracle_activity,
    load_oracle_sessions,
    load_oracle_storage,
    load_oracle_users,
)
from app.core.permissions import Permission
from app.dependencies.permissions import require_permission


router = APIRouter(
    prefix="/databases",
    tags=["Oracle DBA"],
)


@router.get(
    "/{connection_id}/oracle/sessions",
    response_model=OracleSessionsResponse,
)
async def get_sessions(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_oracle_sessions(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}/oracle/storage",
    response_model=OracleStorageResponse,
)
async def get_storage(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_oracle_storage(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}/oracle/activity",
    response_model=OracleActivityResponse,
)
async def get_activity(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await load_oracle_activity(
        request.app.state.database,
        connection_id,
    )

@router.get(
    "/{connection_id}/oracle/users",
    response_model=OracleDatabaseUsersResponse,
)
async def get_database_users(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await load_oracle_users(
        request.app.state.database,
        connection_id,
    )
