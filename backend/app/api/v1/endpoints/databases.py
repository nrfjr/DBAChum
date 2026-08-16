from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.schemas.database_overview import (
    DatabaseOverviewResponse,
)
from app.schemas.user import UserResponse
from app.services.database_overview import (
    get_database_overview,
    list_database_overviews,
)


router = APIRouter(
    prefix="/databases",
    tags=["Databases"],
)


@router.get(
    "/overview",
    response_model=list[DatabaseOverviewResponse],
)
async def get_database_overview_list(
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    return await list_database_overviews(
        request.app.state.database
    )


@router.get(
    "/{connection_id}/overview",
    response_model=DatabaseOverviewResponse,
)
async def get_database_overview_detail(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
):
    return await get_database_overview(
        request.app.state.database,
        connection_id,
    )