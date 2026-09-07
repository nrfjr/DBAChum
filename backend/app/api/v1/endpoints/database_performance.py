from fastapi import APIRouter, Depends, Query, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.database_performance import SqlPlanRequest, SqlPlanResponse, TopSqlResponse
from app.schemas.user import UserResponse
from app.services.database_performance import load_sql_plan, load_top_sql


router = APIRouter(prefix="/databases", tags=["Database Performance"])


@router.get(
    "/{connection_id}/performance/top-sql",
    response_model=TopSqlResponse,
)
async def top_sql(
    connection_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await load_top_sql(request.app.state.database, connection_id, limit=limit)


@router.post(
    "/{connection_id}/performance/plan",
    response_model=SqlPlanResponse,
)
async def sql_plan(
    connection_id: str,
    data: SqlPlanRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await load_sql_plan(request.app.state.database, connection_id, data)
