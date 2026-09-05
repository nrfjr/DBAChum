from fastapi import APIRouter, Depends, Request, Response, status

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.provisioning import (
    LdapProfileCreate,
    LdapProfileResponse,
    LdapProfileTestResponse,
    LdapProfileUpdate,
    LdapSettingsResponse,
    LdapSettingsUpdate,
    OracleMetadataColumn,
    OracleMetadataSchema,
    OracleMetadataSequence,
    OracleMetadataTable,
    ProvisioningProfileCreate,
    ProvisioningProfileResponse,
    ProvisioningProfileUpdate,
    ProvisioningSourceOption,
)
from app.schemas.user import UserResponse
from app.services.provisioning import (
    create_ldap_profile,
    create_provisioning_profile,
    delete_ldap_profile,
    delete_provisioning_profile,
    get_ldap_settings,
    list_ldap_profiles,
    list_provisioning_profiles,
    list_provisioning_sources,
    load_oracle_columns,
    load_oracle_schemas,
    load_oracle_sequences,
    load_oracle_tables,
    test_ldap_profile,
    update_ldap_profile,
    update_ldap_settings,
    update_provisioning_profile,
)

router = APIRouter(prefix="/provisioning", tags=["provisioning"])


@router.get("/profiles", response_model=list[ProvisioningProfileResponse])
async def list_profiles(
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await list_provisioning_profiles(request.app.state.database)


@router.post(
    "/profiles",
    response_model=ProvisioningProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_profile(
    data: ProvisioningProfileCreate,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await create_provisioning_profile(request.app.state.database, data)


@router.put("/profiles/{profile_id}", response_model=ProvisioningProfileResponse)
async def update_profile(
    profile_id: str,
    data: ProvisioningProfileUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await update_provisioning_profile(
        request.app.state.database, profile_id, data
    )


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    await delete_provisioning_profile(request.app.state.database, profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sources", response_model=list[ProvisioningSourceOption])
async def get_sources(
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return list_provisioning_sources()


@router.get("/ldap-profiles", response_model=list[LdapProfileResponse])
async def read_ldap_profiles(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.LDAP_MANAGE)),
):
    return await list_ldap_profiles(request.app.state.database)


@router.post(
    "/ldap-profiles",
    response_model=LdapProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ldap(
    data: LdapProfileCreate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.LDAP_MANAGE)),
):
    return await create_ldap_profile(request.app.state.database, data)


@router.put("/ldap-profiles/{profile_id}", response_model=LdapProfileResponse)
async def update_ldap(
    profile_id: str,
    data: LdapProfileUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.LDAP_MANAGE)),
):
    return await update_ldap_profile(request.app.state.database, profile_id, data)


@router.delete("/ldap-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ldap(
    profile_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.LDAP_MANAGE)),
):
    await delete_ldap_profile(request.app.state.database, profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ldap-profiles/{profile_id}/test", response_model=LdapProfileTestResponse)
async def test_ldap(
    profile_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.LDAP_MANAGE)),
):
    return await test_ldap_profile(request.app.state.database, profile_id)


@router.get("/ldap", response_model=LdapSettingsResponse)
async def read_legacy_ldap(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.LDAP_MANAGE)),
):
    return await get_ldap_settings(request.app.state.database)


@router.put("/ldap", response_model=LdapSettingsResponse)
async def write_legacy_ldap(
    data: LdapSettingsUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.LDAP_MANAGE)),
):
    return await update_ldap_settings(request.app.state.database, data)


@router.get(
    "/oracle/{connection_id}/schemas",
    response_model=list[OracleMetadataSchema],
)
async def oracle_schemas(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await load_oracle_schemas(request.app.state.database, connection_id)


@router.get(
    "/oracle/{connection_id}/schemas/{owner}/tables",
    response_model=list[OracleMetadataTable],
)
async def oracle_tables(
    connection_id: str,
    owner: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await load_oracle_tables(request.app.state.database, connection_id, owner)


@router.get(
    "/oracle/{connection_id}/schemas/{owner}/sequences",
    response_model=list[OracleMetadataSequence],
)
async def oracle_sequences(
    connection_id: str,
    owner: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await load_oracle_sequences(
        request.app.state.database, connection_id, owner
    )


@router.get(
    "/oracle/{connection_id}/schemas/{owner}/tables/{table_name}/columns",
    response_model=list[OracleMetadataColumn],
)
async def oracle_columns(
    connection_id: str,
    owner: str,
    table_name: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.PROVISIONING_MANAGE)
    ),
):
    return await load_oracle_columns(
        request.app.state.database, connection_id, owner, table_name
    )
