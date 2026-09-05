from fastapi import APIRouter, Depends, Query, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.email_delivery import (
    EmailDeliveryClearRequest,
    EmailDeliveryClearResponse,
    EmailDeliveryResponse,
    EmailSettingsResponse,
    EmailSettingsUpdate,
    EmailTestRequest,
    EmailTestResponse,
)
from app.schemas.user import UserResponse
from app.services.email_delivery import (
    clear_email_deliveries,
    list_email_deliveries,
    retry_email_delivery,
    send_test_email,
)
from app.services.email_settings import (
    get_email_settings,
    update_email_settings,
)


router = APIRouter(
    prefix="/notification-delivery",
    tags=["Notification Delivery"],
)


@router.get(
    "/email",
    response_model=EmailSettingsResponse,
)
async def email_settings(
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.NOTIFICATION_MANAGE)
    ),
):
    return await get_email_settings(
        request.app.state.database
    )


@router.put(
    "/email",
    response_model=EmailSettingsResponse,
)
async def save_email_settings(
    data: EmailSettingsUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.NOTIFICATION_MANAGE)
    ),
):
    return await update_email_settings(
        request.app.state.database,
        data,
        updated_by=current_user.username,
    )


@router.post(
    "/email/test",
    response_model=EmailTestResponse,
)
async def test_email_delivery(
    data: EmailTestRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.NOTIFICATION_MANAGE)
    ),
):
    return await send_test_email(
        request.app.state.database,
        recipient_email=str(data.recipient_email),
        recipient_name=data.recipient_name,
        requested_by=current_user.username,
    )


@router.get(
    "/email/deliveries",
    response_model=list[EmailDeliveryResponse],
)
async def email_delivery_history(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserResponse = Depends(
        require_permission(Permission.NOTIFICATION_MANAGE)
    ),
):
    return await list_email_deliveries(
        request.app.state.database,
        limit=limit,
    )


@router.post(
    "/email/deliveries/clear",
    response_model=EmailDeliveryClearResponse,
)
async def clear_email_delivery_history(
    data: EmailDeliveryClearRequest,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.NOTIFICATION_MANAGE)
    ),
):
    return await clear_email_deliveries(
        request.app.state.database,
        delivery_ids=data.delivery_ids,
        clear_all=data.clear_all,
    )


@router.post(
    "/email/deliveries/{delivery_id}/retry",
    response_model=EmailDeliveryResponse,
)
async def retry_failed_email_delivery(
    delivery_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(Permission.NOTIFICATION_MANAGE)
    ),
):
    return await retry_email_delivery(
        request.app.state.database,
        delivery_id,
    )
