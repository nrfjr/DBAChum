from fastapi import APIRouter, Depends, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.database_backup import DatabaseBackupResponse
from app.schemas.user import UserResponse
from app.services.database_backups import load_database_backups


router = APIRouter(
    prefix="/databases",
    tags=["Database Backup Monitoring"],
)


@router.get(
    "/{connection_id}/backups",
    response_model=DatabaseBackupResponse,
)
async def backups(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.MONITOR_READ)
    ),
):
    return await load_database_backups(
        request.app.state.database,
        connection_id,
    )
