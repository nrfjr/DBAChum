from fastapi import APIRouter, Depends, Query, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.database_action import (
    DatabaseActionAuditResponse,
)
from app.schemas.user import UserResponse
from app.services.database_actions import (
    list_database_actions,
)
from app.services.database_connections import (
    get_database_connection,
)


router = APIRouter(
    prefix="/databases",
    tags=["Database Actions"],
)


@router.get(
    "/{connection_id}/actions",
    response_model=list[DatabaseActionAuditResponse],
)
async def get_database_actions(
    connection_id: str,
    request: Request,
    limit: int = Query(
        default=50,
        ge=1,
        le=100,
    ),
    current_user: UserResponse = Depends(
        require_permission(Permission.DBA_OPERATE)
    ),
):
    database = request.app.state.database

    await get_database_connection(
        database,
        connection_id,
    )

    return await list_database_actions(
        database,
        connection_id,
        limit=limit,
    )
