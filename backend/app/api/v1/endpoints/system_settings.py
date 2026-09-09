from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.system_settings import (
    CleanupRequest,
    DataSettingsUpdate,
    GeneralSettingsUpdate,
    MonitoringSettingsUpdate,
)
from app.schemas.user import UserResponse
from app.services.image_uploads import read_image_upload
from app.services.system_settings import (
    data_settings_response,
    delete_branding_logo,
    export_system_metadata,
    general_settings_response,
    maintenance_diagnostics,
    monitoring_settings_response,
    run_system_cleanup,
    save_branding_logo,
    update_data_settings,
    update_general_settings,
    update_monitoring_settings,
    verify_system_indexes,
)


router = APIRouter(prefix="/settings", tags=["Settings"])


def _username(user: UserResponse) -> str:
    return str(user.username)


@router.get("/general")
async def get_general_settings(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await general_settings_response(request.app.state.database)


@router.patch("/general")
async def patch_general_settings(
    payload: GeneralSettingsUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await update_general_settings(
        request.app.state.database,
        payload,
        username=_username(current_user),
    )


@router.get("/monitoring")
async def get_monitoring_settings(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await monitoring_settings_response(request.app.state.database)


@router.patch("/monitoring")
async def patch_monitoring_settings(
    payload: MonitoringSettingsUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await update_monitoring_settings(
        request.app.state.database,
        payload,
        username=_username(current_user),
    )


@router.get("/data")
async def get_data_settings(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await data_settings_response(request.app.state.database)


@router.patch("/data")
async def patch_data_settings(
    payload: DataSettingsUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await update_data_settings(
        request.app.state.database,
        payload,
        username=_username(current_user),
    )


@router.get("/data/export")
async def export_data(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await export_system_metadata(request.app.state.database)


@router.get("/maintenance")
async def get_maintenance(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await maintenance_diagnostics(request.app.state.database)


@router.post("/maintenance/cleanup")
async def cleanup(
    payload: CleanupRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await run_system_cleanup(request.app.state.database, payload)


@router.post("/maintenance/indexes/verify")
async def verify_indexes(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await verify_system_indexes(request.app.state.database)


@router.put("/general/logo")
async def put_general_logo(
    request: Request,
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    content_type, data = await read_image_upload(file)
    return await save_branding_logo(
        request.app.state.database,
        content_type=content_type,
        data=data,
        username=_username(current_user),
    )


@router.delete("/general/logo")
async def remove_general_logo(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SYSTEM_MANAGE)),
):
    return await delete_branding_logo(request.app.state.database)

