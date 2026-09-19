from fastapi import (
    APIRouter,
    Depends,
    File,
    Query,
    Request,
    UploadFile,
    Response,
)

from app.schemas.oracle_dba import (
    OracleActivityResponse,
    OracleAdvisorsResponse,
    OracleSessionsResponse,
    OracleStorageResponse,
    OracleDatabaseUsersResponse,
    OracleUserListColumnRequest,
    OracleUserListColumnsRequest,
    OracleUserListColumnResponse,
    OracleUserListColumnPreviewResponse,
    OracleUserListColumnsPreviewResponse,
    OracleUserListColumnsCreateResponse,
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
    OracleUsernameAvailabilityResponse,
    OracleUserAccessInspectorResponse,
    OracleAccessLookupResponse,
    OracleAccessCompareResponse,
    OracleRoleListResponse,
    OracleRoleDetailResponse,
    OracleRoleCreateRequest,
    OracleRoleChangeRequest,
    OracleRoleChangePreviewResponse,
    OracleRoleCreateResponse,
    OracleRoleChangeResponse,
    OracleRoleDropRequest,
    OracleRoleDropPreviewResponse,
    OracleRoleDropResponse,
)
from app.schemas.provisioning import (
    ProvisioningExecuteRequest,
    ProvisioningExecutionResponse,
    ProvisioningHistoryClearRequest,
    ProvisioningHistoryClearResponse,
    ProvisioningPreviewRequest,
    ProvisioningPreviewResponse,
    ProvisioningProfileResponse,
    ProvisioningRetryRequest,
    ProvisioningRetryRequirement,
    ProvisioningRunDetail,
    ProvisioningRunSummary,
    ProvisioningDeprovisionPreviewResponse,
    OracleUserDeprovisionProfileOption,
    OracleUserDeprovisionPreviewResponse,
    OracleUserDeprovisionRequest,
    OracleUserDeprovisionResponse,
    OracleProvisionedDetailsResponse,
    OracleProvisionedDetailsEditRequest,
    OracleProvisionedDetailsPreviewResponse,
    OracleProvisionedDetailsEditResponse,
    BulkProvisionImportResponse,
    BulkProvisionRequest,
    BulkProvisionPreviewResponse,
    BulkProvisionExecutionResponse,
    BulkProvisionExportRequest,
    OracleMetadataSchema,
    OracleMetadataTable,
    OracleMetadataColumn,
)
from app.schemas.user import UserResponse
from app.services.oracle_dba import (
    load_oracle_activity,
    load_oracle_advisors,
    load_oracle_sessions,
    load_oracle_storage,
    load_oracle_users,
    load_oracle_reference_user,
    provision_oracle_user,
    get_oracle_target,
)
from app.services.provisioning import list_provisioning_profiles_for_connection
from app.connectors.oracle_provisioning import normalize_oracle_identifier, oracle_user_exists
from app.connectors.oracle_users import get_oracle_users
from app.services.oracle_access_inspector import load_oracle_user_access_inspector
from app.services.oracle_access_lookup import load_oracle_access_lookup
from app.services.oracle_access_compare import load_oracle_access_compare
from app.services.oracle_role_management import (
    load_oracle_roles,
    load_oracle_role_detail,
    build_oracle_role_create_preview,
    execute_oracle_role_create,
    build_oracle_role_change_preview,
    execute_oracle_role_change,
    build_oracle_role_drop_preview,
    execute_oracle_role_drop,
)
from app.services.oracle_user_list_columns import (
    create_oracle_user_list_column,
    create_oracle_user_list_columns,
    delete_oracle_user_list_column,
    preview_oracle_user_list_column,
    preview_oracle_user_list_columns,
    list_user_list_source_schemas_for_connection,
    list_user_list_source_tables_for_connection,
    list_user_list_source_columns_for_connection,
)
from app.services.oracle_user_lifecycle import (
    load_oracle_user_lifecycle_state,
    build_oracle_user_edit_preview,
    execute_oracle_user_edit,
    execute_oracle_user_password_reset,
    execute_oracle_user_lifecycle_action,
)
from app.services.provisioning_preview import build_provisioning_preview
from app.services.bulk_provisioning import (
    execute_bulk_provisioning,
    import_bulk_provision_file,
    preview_bulk_provisioning,
    build_bulk_template_xlsx,
    build_bulk_results_xlsx,
)
from app.services.provisioning_execution import execute_provisioning_profile
from app.services.deprovisioning import (
    build_oracle_user_deprovision_preview,
    execute_oracle_user_deprovision,
    list_oracle_user_deprovision_profiles,
)
from app.services.provisioned_details import (
    load_oracle_user_provisioned_details,
    build_oracle_user_provisioned_details_preview,
    execute_oracle_user_provisioned_details_edit,
)
from app.services.provisioning_lifecycle import (
    build_deprovision_preview,
    clear_provisioning_runs,
    get_provisioning_run,
    get_retry_requirement,
    list_provisioning_runs,
    retry_provisioning_run,
)
from app.core.exceptions import AppError
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
    "/{connection_id}/oracle/advisors",
    response_model=OracleAdvisorsResponse,
)
async def get_advisors(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.MONITOR_READ)
    ),
):
    return await load_oracle_advisors(
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
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await load_oracle_users(
        request.app.state.database,
        connection_id,
    )

@router.get(
    "/{connection_id}/oracle/user-list-source/{source_connection_id}/schemas",
    response_model=list[OracleMetadataSchema],
)
async def get_user_list_source_schemas(
    connection_id: str,
    source_connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await list_user_list_source_schemas_for_connection(
        request.app.state.database,
        connection_id,
        source_connection_id,
    )


@router.get(
    "/{connection_id}/oracle/user-list-source/{source_connection_id}/schemas/{owner}/tables",
    response_model=list[OracleMetadataTable],
)
async def get_user_list_source_tables(
    connection_id: str,
    source_connection_id: str,
    owner: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await list_user_list_source_tables_for_connection(
        request.app.state.database,
        connection_id,
        source_connection_id,
        owner,
    )


@router.get(
    "/{connection_id}/oracle/user-list-source/{source_connection_id}/schemas/{owner}/tables/{table_name}/columns",
    response_model=list[OracleMetadataColumn],
)
async def get_user_list_source_columns(
    connection_id: str,
    source_connection_id: str,
    owner: str,
    table_name: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await list_user_list_source_columns_for_connection(
        request.app.state.database,
        connection_id,
        source_connection_id,
        owner,
        table_name,
    )


@router.post(
    "/{connection_id}/oracle/user-list-columns/preview",
    response_model=OracleUserListColumnPreviewResponse,
)
async def preview_user_list_column(
    connection_id: str,
    data: OracleUserListColumnRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    connection = await get_oracle_target(
        request.app.state.database,
        connection_id,
    )
    users = await get_oracle_users(connection)
    if not users.get("available"):
        raise AppError(
            users.get("warning") or "Oracle user inventory is unavailable.",
            code="ORACLE_USER_LIST_PREVIEW_UNAVAILABLE",
            status_code=400,
        )
    return await preview_oracle_user_list_column(
        request.app.state.database,
        connection_id,
        source_connection_id=data.source_connection_id,
        base_column=data.base_column,
        owner=data.owner,
        table_name=data.table_name,
        join_column=data.join_column,
        display_column=data.display_column,
        label=data.label,
        base_users=users.get("items") or [],
    )


@router.post(
    "/{connection_id}/oracle/user-list-columns/preview-batch",
    response_model=OracleUserListColumnsPreviewResponse,
)
async def preview_user_list_columns(
    connection_id: str,
    data: OracleUserListColumnsRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    connection = await get_oracle_target(
        request.app.state.database,
        connection_id,
    )
    users = await get_oracle_users(connection)
    if not users.get("available"):
        raise AppError(
            users.get("warning") or "Oracle user inventory is unavailable.",
            code="ORACLE_USER_LIST_PREVIEW_UNAVAILABLE",
            status_code=400,
        )
    return await preview_oracle_user_list_columns(
        request.app.state.database,
        connection_id,
        source_connection_id=data.source_connection_id,
        base_column=data.base_column,
        owner=data.owner,
        table_name=data.table_name,
        join_column=data.join_column,
        columns=[item.model_dump() for item in data.columns],
        base_users=users.get("items") or [],
    )


@router.post(
    "/{connection_id}/oracle/user-list-columns/batch",
    response_model=OracleUserListColumnsCreateResponse,
)
async def add_user_list_columns(
    connection_id: str,
    data: OracleUserListColumnsRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    items = await create_oracle_user_list_columns(
        request.app.state.database,
        connection_id,
        source_connection_id=data.source_connection_id,
        base_column=data.base_column,
        owner=data.owner,
        table_name=data.table_name,
        join_column=data.join_column,
        columns=[item.model_dump() for item in data.columns],
        created_by=current_user.username,
    )
    return {"items": items}


@router.post(
    "/{connection_id}/oracle/user-list-columns",
    response_model=OracleUserListColumnResponse,
)
async def add_user_list_column(
    connection_id: str,
    data: OracleUserListColumnRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await create_oracle_user_list_column(
        request.app.state.database,
        connection_id,
        source_connection_id=data.source_connection_id,
        base_column=data.base_column,
        owner=data.owner,
        table_name=data.table_name,
        join_column=data.join_column,
        display_column=data.display_column,
        label=data.label,
        created_by=current_user.username,
    )


@router.delete(
    "/{connection_id}/oracle/user-list-columns/{column_id}",
)
async def remove_user_list_column(
    connection_id: str,
    column_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    await delete_oracle_user_list_column(
        request.app.state.database,
        connection_id,
        column_id,
    )
    return {"deleted": True}


@router.get(
    "/{connection_id}/oracle/users/{username}/availability",
    response_model=OracleUsernameAvailabilityResponse,
)
async def get_oracle_username_availability(
    connection_id: str,
    username: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    normalized = normalize_oracle_identifier(username, field_name="Username")
    connection = await get_oracle_target(request.app.state.database, connection_id)
    exists = await oracle_user_exists(connection, normalized)
    return OracleUsernameAvailabilityResponse(
        username=normalized,
        available=not exists,
        message=None if not exists else "This Oracle username already exists.",
    )


@router.get(
    "/{connection_id}/oracle/bulk-provision/template.xlsx",
)
async def download_oracle_bulk_provision_template(
    connection_id: str,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    content = build_bulk_template_xlsx()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="dbachum-bulk-user-template.xlsx"'},
    )


@router.post(
    "/{connection_id}/oracle/bulk-provision/results.xlsx",
)
async def download_oracle_bulk_provision_results(
    connection_id: str,
    data: BulkProvisionExportRequest,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    rows = [item.model_dump() for item in data.rows]
    content = build_bulk_results_xlsx(rows)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="dbachum-bulk-provision-results.xlsx"'},
    )


@router.post(
    "/{connection_id}/oracle/bulk-provision/import",
    response_model=BulkProvisionImportResponse,
)
async def import_oracle_bulk_provision_file(
    connection_id: str,
    request: Request,
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await import_bulk_provision_file(
        request.app.state.database, connection_id, file
    )


@router.post(
    "/{connection_id}/oracle/bulk-provision/preview",
    response_model=BulkProvisionPreviewResponse,
)
async def preview_oracle_bulk_provisioning(
    connection_id: str,
    data: BulkProvisionRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await preview_bulk_provisioning(
        request.app.state.database,
        connection_id,
        data,
        current_user,
        requester_ip=request.client.host if request.client else None,
    )


@router.post(
    "/{connection_id}/oracle/bulk-provision/execute",
    response_model=BulkProvisionExecutionResponse,
)
async def execute_oracle_bulk_provisioning(
    connection_id: str,
    data: BulkProvisionRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await execute_bulk_provisioning(
        request.app.state.database,
        connection_id,
        data,
        current_user,
        requester_ip=request.client.host if request.client else None,
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
        require_permission(Permission.DATABASE_INSPECT)
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
    "/{connection_id}/oracle/users/{username}/access-inspector",
    response_model=OracleUserAccessInspectorResponse,
)
async def get_oracle_user_access_inspector_endpoint(
    connection_id: str,
    username: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await load_oracle_user_access_inspector(
        request.app.state.database,
        connection_id,
        username,
    )


@router.get(
    "/{connection_id}/oracle/access-lookup",
    response_model=OracleAccessLookupResponse,
)
async def get_oracle_access_lookup_endpoint(
    connection_id: str,
    request: Request,
    kind: str = Query(..., max_length=32),
    value: str | None = Query(default=None, max_length=128),
    owner: str | None = Query(default=None, max_length=30),
    object_name: str | None = Query(default=None, max_length=30),
    privilege: str | None = Query(default=None, max_length=128),
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await load_oracle_access_lookup(
        request.app.state.database,
        connection_id,
        kind=kind,
        value=value,
        owner=owner,
        object_name=object_name,
        privilege=privilege,
    )


@router.get(
    "/{connection_id}/oracle/access-compare",
    response_model=OracleAccessCompareResponse,
)
async def get_oracle_access_compare_endpoint(
    connection_id: str,
    request: Request,
    left_username: str = Query(..., min_length=1, max_length=30),
    right_username: str = Query(..., min_length=1, max_length=30),
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await load_oracle_access_compare(
        request.app.state.database,
        connection_id,
        left_username,
        right_username,
    )


@router.get(
    "/{connection_id}/oracle/roles",
    response_model=OracleRoleListResponse,
)
async def get_oracle_roles_endpoint(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DATABASE_INSPECT)),
):
    return await load_oracle_roles(request.app.state.database, connection_id)


@router.post(
    "/{connection_id}/oracle/roles/create-preview",
    response_model=OracleRoleChangePreviewResponse,
)
async def preview_oracle_role_create_endpoint(
    connection_id: str,
    data: OracleRoleCreateRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await build_oracle_role_create_preview(request.app.state.database, connection_id, data)



@router.get(
    "/{connection_id}/oracle/roles/{role_name}",
    response_model=OracleRoleDetailResponse,
)
async def get_oracle_role_detail_endpoint(
    connection_id: str,
    role_name: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DATABASE_INSPECT)),
):
    return await load_oracle_role_detail(request.app.state.database, connection_id, role_name)


@router.post(
    "/{connection_id}/oracle/roles",
    response_model=OracleRoleCreateResponse,
    status_code=201,
)
async def create_oracle_role_endpoint(
    connection_id: str,
    data: OracleRoleCreateRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await execute_oracle_role_create(
        request.app.state.database, connection_id, data, current_user
    )


@router.post(
    "/{connection_id}/oracle/roles/{role_name}/change-preview",
    response_model=OracleRoleChangePreviewResponse,
)
async def preview_oracle_role_change_endpoint(
    connection_id: str,
    role_name: str,
    data: OracleRoleChangeRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await build_oracle_role_change_preview(
        request.app.state.database, connection_id, role_name, data
    )


@router.post(
    "/{connection_id}/oracle/roles/{role_name}/change",
    response_model=OracleRoleChangeResponse,
)
async def change_oracle_role_endpoint(
    connection_id: str,
    role_name: str,
    data: OracleRoleChangeRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await execute_oracle_role_change(
        request.app.state.database, connection_id, role_name, data, current_user
    )


@router.get(
    "/{connection_id}/oracle/roles/{role_name}/drop-preview",
    response_model=OracleRoleDropPreviewResponse,
)
async def preview_oracle_role_drop_endpoint(
    connection_id: str,
    role_name: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await build_oracle_role_drop_preview(
        request.app.state.database, connection_id, role_name
    )


@router.post(
    "/{connection_id}/oracle/roles/{role_name}/drop",
    response_model=OracleRoleDropResponse,
)
async def drop_oracle_role_endpoint(
    connection_id: str,
    role_name: str,
    data: OracleRoleDropRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await execute_oracle_role_drop(
        request.app.state.database, connection_id, role_name, data, current_user
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
        require_permission(Permission.DATABASE_INSPECT)
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
        require_permission(Permission.DATABASE_INSPECT)
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
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await list_provisioning_runs(
        request.app.state.database,
        connection_id,
    )


@router.post(
    "/{connection_id}/oracle/provisioning-runs/clear",
    response_model=ProvisioningHistoryClearResponse,
)
async def clear_database_provisioning_runs(
    connection_id: str,
    data: ProvisioningHistoryClearRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await clear_provisioning_runs(
        request.app.state.database,
        connection_id,
        run_ids=data.run_ids,
        clear_all=data.clear_all,
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
        require_permission(Permission.DATABASE_INSPECT)
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
        require_permission(Permission.DATABASE_INSPECT)
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
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await build_deprovision_preview(
        request.app.state.database,
        connection_id,
        run_id,
    )


@router.get(
    "/{connection_id}/oracle/users/{username}/provisioned-details",
    response_model=OracleProvisionedDetailsResponse,
)
async def get_oracle_user_provisioned_details(
    connection_id: str,
    username: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await load_oracle_user_provisioned_details(
        request.app.state.database,
        connection_id,
        username,
    )


@router.post(
    "/{connection_id}/oracle/users/{username}/provisioned-details/preview",
    response_model=OracleProvisionedDetailsPreviewResponse,
)
async def preview_oracle_user_provisioned_details(
    connection_id: str,
    username: str,
    data: OracleProvisionedDetailsEditRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await build_oracle_user_provisioned_details_preview(
        request.app.state.database,
        connection_id,
        username,
        data,
    )


@router.post(
    "/{connection_id}/oracle/users/{username}/provisioned-details",
    response_model=OracleProvisionedDetailsEditResponse,
)
async def edit_oracle_user_provisioned_details(
    connection_id: str,
    username: str,
    data: OracleProvisionedDetailsEditRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    return await execute_oracle_user_provisioned_details_edit(
        request.app.state.database,
        connection_id,
        username,
        data,
        current_user,
    )


@router.get(
    "/{connection_id}/oracle/users/{username}/deprovision-profiles",
    response_model=list[OracleUserDeprovisionProfileOption],
)
async def get_oracle_user_deprovision_profiles(
    connection_id: str,
    username: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await list_oracle_user_deprovision_profiles(
        request.app.state.database,
        connection_id,
        username,
    )


@router.get(
    "/{connection_id}/oracle/users/{username}/deprovision-preview",
    response_model=OracleUserDeprovisionPreviewResponse,
)
async def preview_oracle_user_deprovision(
    connection_id: str,
    username: str,
    request: Request,
    profile_id: str | None = Query(default=None, max_length=64),
    account_only: bool = Query(default=False),
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await build_oracle_user_deprovision_preview(
        request.app.state.database,
        connection_id,
        username,
        profile_id=profile_id,
        account_only=account_only,
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
