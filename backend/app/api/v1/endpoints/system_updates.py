from fastapi import APIRouter, Depends, Query

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.user import UserResponse
from app.services.release_updates import check_for_updates


router = APIRouter(prefix="/system/updates", tags=["System Updates"])


@router.get("/check")
async def check_system_update(
    refresh: bool = Query(default=False),
    current_user: UserResponse = Depends(
        require_permission(Permission.SYSTEM_MANAGE)
    ),
):
    return await check_for_updates(force_refresh=refresh)
