from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.user import UserResponse
from app.services.release_updates import check_for_updates
from app.services.update_installation import (
    get_update_install_status,
    queue_update_install,
)


router = APIRouter(prefix="/system/updates", tags=["System Updates"])


class UpdateInstallRequest(BaseModel):
    version: str = Field(min_length=5, max_length=32)


@router.get("/check")
async def check_system_update(
    refresh: bool = Query(default=False),
    current_user: UserResponse = Depends(
        require_permission(Permission.SYSTEM_MANAGE)
    ),
):
    return await check_for_updates(force_refresh=refresh)


@router.get("/install/status")
async def system_update_install_status(
    current_user: UserResponse = Depends(
        require_permission(Permission.SYSTEM_MANAGE)
    ),
):
    return get_update_install_status()


@router.post("/install", status_code=status.HTTP_202_ACCEPTED)
async def install_system_update(
    payload: UpdateInstallRequest,
    current_user: UserResponse = Depends(
        require_permission(Permission.SYSTEM_MANAGE)
    ),
):
    return await queue_update_install(payload.version)
