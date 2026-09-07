from fastapi import APIRouter, Depends, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.database_parameter import DatabaseParametersResponse
from app.schemas.user import UserResponse
from app.services.database_parameters import load_database_parameters


router = APIRouter(prefix="/databases", tags=["Database Parameters"])


@router.get(
    "/{connection_id}/parameters",
    response_model=DatabaseParametersResponse,
)
async def parameters(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.DATABASE_INSPECT)
    ),
):
    return await load_database_parameters(
        request.app.state.database,
        connection_id,
    )
