from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)

from app.dependencies.auth import get_current_user
from app.schemas.database_overview import (
    DatabaseOverviewResponse,
)
from app.schemas.database_metrics import (
    DatabaseMetricHistoryResponse,
)
from app.schemas.user import UserResponse
from app.services.database_overview import (
    get_database_overview,
    list_database_overviews,
)
from app.services.database_metrics import (
    get_database_metric_history,
)
from app.core.permissions import Permission
from app.dependencies.permissions import require_permission

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
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
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
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await get_database_overview(
        request.app.state.database,
        connection_id,
    )

@router.get(
    "/{connection_id}/metrics/history",
    response_model=(
        DatabaseMetricHistoryResponse
    ),
)
async def get_database_metrics_history(
    connection_id: str,
    request: Request,

    hours: int = Query(
        default=24,
        ge=1,
        le=168,
    ),

    limit: int = Query(
        default=2000,
        ge=1,
        le=5000,
    ),

    current_user: UserResponse = Depends(
        require_permission(
            Permission.MONITOR_READ
        )
    ),
):
    return await get_database_metric_history(
        request.app.state.database,
        connection_id,
        hours,
        limit,
    )