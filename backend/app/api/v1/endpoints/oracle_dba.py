from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from app.dependencies.auth import (
    get_current_user,
)
from app.schemas.oracle_dba import (
    OracleActivityResponse,
    OracleSessionsResponse,
    OracleStorageResponse,
)
from app.schemas.user import UserResponse
from app.services.oracle_dba import (
    load_oracle_activity,
    load_oracle_sessions,
    load_oracle_storage,
)


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
    current_user: UserResponse = Depends(
        get_current_user
    ),
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
    current_user: UserResponse = Depends(
        get_current_user
    ),
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
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    return await load_oracle_activity(
        request.app.state.database,
        connection_id,
    )