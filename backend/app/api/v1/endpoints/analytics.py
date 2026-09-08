import json

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.user import UserResponse
from app.services.analytics import (
    get_database_analytics,
    get_server_analytics,
    growth_import_preview,
    import_database_growth,
)


router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/databases")
async def database_analytics(
    request: Request,
    engine: str | None = Query(default=None, pattern="^(oracle|sqlserver|mysql)$"),
    months: int = Query(default=12, ge=1, le=60),
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await get_database_analytics(
        request.app.state.database,
        engine=engine,
        months=months,
    )


@router.get("/servers")
async def server_analytics(
    request: Request,
    os_family: str | None = Query(default=None, pattern="^(windows|linux|aix|unix|other)$"),
    months: int = Query(default=12, ge=1, le=60),
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await get_server_analytics(
        request.app.state.database,
        os_family=os_family,
        months=months,
    )


@router.post("/database-growth/preview")
async def preview_database_growth(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(require_permission(Permission.CONNECTION_MANAGE)),
):
    content = await file.read()
    return growth_import_preview(file.filename or "growth.csv", content)


@router.post("/database-growth/import")
async def import_database_growth_endpoint(
    request: Request,
    file: UploadFile = File(...),
    config_json: str = Form(...),
    current_user: UserResponse = Depends(require_permission(Permission.CONNECTION_MANAGE)),
):
    config = json.loads(config_json)
    content = await file.read()
    return await import_database_growth(
        request.app.state.database,
        file.filename or "growth.csv",
        content,
        config,
    )
