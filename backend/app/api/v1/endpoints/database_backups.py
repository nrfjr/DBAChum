from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

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
    window: Literal["today", "3d", "7d", "custom"] = Query("today"),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: UserResponse = Depends(
        require_permission(Permission.MONITOR_READ)
    ),
):
    return await load_database_backups(
        request.app.state.database,
        connection_id,
        window=window,
        start_date=start_date,
        end_date=end_date,
    )
