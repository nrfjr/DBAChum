from fastapi import APIRouter, Depends, Request, Response, status

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.record import (
    RecordCreate,
    RecordResponse,
    RecordSecretResponse,
    RecordUpdate,
)
from app.schemas.user import UserResponse
from app.services.records import (
    create_record,
    delete_record,
    get_record_response,
    list_records,
    reveal_record_password,
    update_record,
)


router = APIRouter(
    prefix="/records",
    tags=["Records"],
)


@router.get("", response_model=list[RecordResponse])
async def get_records(
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.MONITOR_READ)
    ),
):
    return await list_records(request.app.state.database)


@router.get("/{record_id}", response_model=RecordResponse)
async def get_record_detail(
    record_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.MONITOR_READ)
    ),
):
    return await get_record_response(
        request.app.state.database,
        record_id,
    )


@router.post(
    "",
    response_model=RecordResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_record_endpoint(
    data: RecordCreate,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.RECORD_MANAGE)
    ),
):
    return await create_record(
        request.app.state.database,
        data,
        created_by=current_user.username,
    )


@router.put("/{record_id}", response_model=RecordResponse)
async def update_record_endpoint(
    record_id: str,
    data: RecordUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.RECORD_MANAGE)
    ),
):
    return await update_record(
        request.app.state.database,
        record_id,
        data,
        updated_by=current_user.username,
    )


@router.delete(
    "/{record_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_record_endpoint(
    record_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.RECORD_MANAGE)
    ),
):
    await delete_record(request.app.state.database, record_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{record_id}/reveal-password",
    response_model=RecordSecretResponse,
)
async def reveal_record_password_endpoint(
    record_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.RECORD_MANAGE)
    ),
):
    password = await reveal_record_password(
        request.app.state.database,
        record_id,
    )
    return RecordSecretResponse(password=password)
