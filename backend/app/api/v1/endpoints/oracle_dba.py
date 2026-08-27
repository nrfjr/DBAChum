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
    OracleUserLifecycleStateResponse,
    OracleUserEditRequest,
    OracleUserEditExecuteRequest,
    OracleUserEditPreviewResponse,
    OracleUserEditResponse,
    OracleUserPasswordResetRequest,
    OracleUserAccountActionRequest,
    OracleUserLifecycleActionResponse,
)
from app.schemas.provisioning import (
    ProvisioningExecuteRequest,
    ProvisioningExecutionResponse,
    ProvisioningPreviewRequest,
    ProvisioningPreviewResponse,
    ProvisioningProfileResponse,
    ProvisioningRetryRequest,
    ProvisioningRetryRequirement,
    ProvisioningRunDetail,
    ProvisioningRunSummary,
    ProvisioningDeprovisionPreviewResponse,
    OracleUserDeprovisionPreviewResponse,
    OracleUserDeprovisionRequest,
    OracleUserDeprovisionResponse,
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
from app.services.oracle_user_lifecycle import (
    load_oracle_user_lifecycle_state,
    build_oracle_user_edit_preview,
    execute_oracle_user_edit,
    execute_oracle_user_password_reset,
    execute_oracle_user_lifecycle_action,
)
from app.services.provisioning_preview import build_provisioning_preview
from app.services.provisioning_execution import execute_provisioning_profile
from app.services.deprovisioning import (
    build_oracle_user_deprovision_preview,
    execute_oracle_user_deprovision,
)
from app.services.provisioning_lifecycle import (
    build_deprovision_preview,
    get_provisioning_run,
    get_retry_requirement,
    list_provisioning_runs,
    retry_provisioning_run,
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

@router.get(
    "/{connection_id}/oracle/users/{username}/lifecycle",
    response_model=OracleUserLifecycleStateResponse,
)
async def get_oracle_user_lifecycle(
    connection_id: str,
    username: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await load_oracle_user_lifecycle_state(
        request.app.state.database, connection_id, username
    )


@router.post(
    "/{connection_id}/oracle/users/{username}/edit-preview",
    response_model=OracleUserEditPreviewResponse,
)
async def preview_oracle_user_edit(
    connection_id: str,
    username: str,
    data: OracleUserEditRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await build_oracle_user_edit_preview(
        request.app.state.database, connection_id, username, data
    )


@router.post(
    "/{connection_id}/oracle/users/{username}/edit",
    response_model=OracleUserEditResponse,
)
async def edit_oracle_user(
    connection_id: str,
    username: str,
    data: OracleUserEditExecuteRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await execute_oracle_user_edit(
        request.app.state.database, connection_id, username, data, current_user
    )


@router.post(
    "/{connection_id}/oracle/users/{username}/reset-password",
    response_model=OracleUserLifecycleActionResponse,
)
async def reset_oracle_user_password_endpoint(
    connection_id: str,
    username: str,
    data: OracleUserPasswordResetRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await execute_oracle_user_password_reset(
        request.app.state.database, connection_id, username, data, current_user
    )


@router.post(
    "/{connection_id}/oracle/users/{username}/account-action",
    response_model=OracleUserLifecycleActionResponse,
)
async def oracle_user_account_action(
    connection_id: str,
    username: str,
    data: OracleUserAccountActionRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await execute_oracle_user_lifecycle_action(
        request.app.state.database, connection_id, username, data, current_user
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
    "/{connection_id}/oracle/provisioning-profiles/{profile_id}/execute",
    response_model=ProvisioningExecutionResponse,
)
async def execute_database_provisioning_profile(
    connection_id: str,
    profile_id: str,
    data: ProvisioningExecuteRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await execute_provisioning_profile(
        request.app.state.database,
        connection_id,
        profile_id,
        data,
        current_user,
        requester_ip=request.client.host if request.client else None,
    )


@router.get(
    "/{connection_id}/oracle/provisioning-runs",
    response_model=list[ProvisioningRunSummary],
)
async def get_database_provisioning_runs(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await list_provisioning_runs(
        request.app.state.database,
        connection_id,
    )


@router.get(
    "/{connection_id}/oracle/provisioning-runs/{run_id}",
    response_model=ProvisioningRunDetail,
)
async def get_database_provisioning_run(
    connection_id: str,
    run_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await get_provisioning_run(
        request.app.state.database,
        connection_id,
        run_id,
    )


@router.get(
    "/{connection_id}/oracle/provisioning-runs/{run_id}/retry-requirement",
    response_model=ProvisioningRetryRequirement,
)
async def get_database_provisioning_retry_requirement(
    connection_id: str,
    run_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await get_retry_requirement(
        request.app.state.database,
        connection_id,
        run_id,
    )


@router.post(
    "/{connection_id}/oracle/provisioning-runs/{run_id}/retry",
    response_model=ProvisioningExecutionResponse,
)
async def retry_database_provisioning_run(
    connection_id: str,
    run_id: str,
    data: ProvisioningRetryRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await retry_provisioning_run(
        request.app.state.database,
        connection_id,
        run_id,
        data,
        current_user,
        requester_ip=request.client.host if request.client else None,
    )


@router.get(
    "/{connection_id}/oracle/provisioning-runs/{run_id}/deprovision-preview",
    response_model=ProvisioningDeprovisionPreviewResponse,
)
async def preview_database_deprovision(
    connection_id: str,
    run_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await build_deprovision_preview(
        request.app.state.database,
        connection_id,
        run_id,
    )


@router.get(
    "/{connection_id}/oracle/users/{username}/deprovision-preview",
    response_model=OracleUserDeprovisionPreviewResponse,
)
async def preview_oracle_user_deprovision(
    connection_id: str,
    username: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await build_oracle_user_deprovision_preview(
        request.app.state.database,
        connection_id,
        username,
    )


@router.post(
    "/{connection_id}/oracle/users/{username}/deprovision",
    response_model=OracleUserDeprovisionResponse,
)
async def deprovision_oracle_user(
    connection_id: str,
    username: str,
    data: OracleUserDeprovisionRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await execute_oracle_user_deprovision(
        request.app.state.database,
        connection_id,
        username,
        data,
        current_user,
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
