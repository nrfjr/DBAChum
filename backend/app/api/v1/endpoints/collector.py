from fastapi import APIRouter, Depends, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.collector import CollectorStatusResponse
from app.schemas.user import UserResponse
from app.services.collector_status import get_collector_status


router = APIRouter(
    prefix="/collector",
    tags=["Collector"],
)


@router.get(
    "/status",
    response_model=CollectorStatusResponse,
)
async def collector_status(
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.MONITOR_READ)
    ),
):
    return await get_collector_status(
        request.app.state.database
    )
