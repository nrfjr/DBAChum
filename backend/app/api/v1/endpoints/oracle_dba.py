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
    OracleReferenceUserResponse,
    OracleCreateUserRequest,
    OracleCreateUserResponse,
)
from app.schemas.provisioning import (
    ProvisioningPreviewRequest,
    ProvisioningPreviewResponse,
    ProvisioningProfileResponse,
)
from app.schemas.user import UserResponse
from app.services.oracle_dba import (
    load_oracle_activity,
    load_oracle_sessions,
    load_oracle_storage,
    load_oracle_users,
    load_oracle_reference_user,
    provision_oracle_user,
)
from app.services.provisioning import list_provisioning_profiles_for_connection
from app.services.provisioning_preview import build_provisioning_preview
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

@router.get(
    "/{connection_id}/oracle/users/reference/{username}",
    response_model=OracleReferenceUserResponse,
)
async def get_reference_user(
    connection_id: str,
    username: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await load_oracle_reference_user(
        request.app.state.database,
        connection_id,
        username,
    )


@router.get(
    "/{connection_id}/oracle/provisioning-profiles",
    response_model=list[ProvisioningProfileResponse],
)
async def get_database_provisioning_profiles(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await list_provisioning_profiles_for_connection(
        request.app.state.database,
        connection_id,
    )


@router.post(
    "/{connection_id}/oracle/provisioning-profiles/{profile_id}/preview",
    response_model=ProvisioningPreviewResponse,
)
async def preview_database_provisioning_profile(
    connection_id: str,
    profile_id: str,
    data: ProvisioningPreviewRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await build_provisioning_preview(
        request.app.state.database,
        profile_id,
        data,
        current_user,
        requester_ip=request.client.host if request.client else None,
        parent_connection_id=connection_id,
    )


@router.post(
    "/{connection_id}/oracle/users",
    response_model=OracleCreateUserResponse,
    status_code=201,
)
async def create_database_user(
    connection_id: str,
    data: OracleCreateUserRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await provision_oracle_user(
        request.app.state.database,
        connection_id,
        data,
        current_user,
        requester_ip=request.client.host if request.client else None,
    )

