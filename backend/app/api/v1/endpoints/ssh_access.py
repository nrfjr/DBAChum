from fastapi import APIRouter, Depends, Request, Response, status

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.ssh_access import (
    SshAccessProfileCreate,
    SshAccessProfileResponse,
    SshAccessProfileUpdate,
)
from app.schemas.user import UserResponse
from app.services.ssh_access import (
    create_ssh_profile,
    delete_ssh_profile,
    list_ssh_profiles,
    update_ssh_profile,
)


router = APIRouter(
    prefix="/ssh-access-profiles",
    tags=["Infrastructure"],
)


@router.get("", response_model=list[SshAccessProfileResponse])
async def get_ssh_access_profiles(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    return await list_ssh_profiles(request.app.state.database)


@router.post(
    "",
    response_model=SshAccessProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ssh_access_profile(
    data: SshAccessProfileCreate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    return await create_ssh_profile(request.app.state.database, data)


@router.put("/{profile_id}", response_model=SshAccessProfileResponse)
async def update_ssh_access_profile(
    profile_id: str,
    data: SshAccessProfileUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    return await update_ssh_profile(request.app.state.database, profile_id, data)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ssh_access_profile(
    profile_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    await delete_ssh_profile(request.app.state.database, profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
