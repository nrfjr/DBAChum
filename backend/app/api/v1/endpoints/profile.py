from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from app.dependencies.auth import get_current_user
from app.schemas.notification import UserNotificationPreferencesUpdate
from app.schemas.user import (
    UserPreferencesUpdate,
    UserProfileUpdate,
    UserResponse,
)
from app.services.users import (
    update_current_user_notifications,
    update_current_user_preferences,
    update_current_user_profile,
)


router = APIRouter(
    prefix="/profile",
    tags=["Profile"],
)


@router.get(
    "",
    response_model=UserResponse,
)
async def get_profile(
    current_user: UserResponse = Depends(
        get_current_user
    ),
) -> UserResponse:
    return current_user


@router.put(
    "",
    response_model=UserResponse,
)
async def update_profile(
    data: UserProfileUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
) -> UserResponse:
    return await update_current_user_profile(
        request.app.state.database,
        current_user.id,
        data,
    )


@router.put(
    "/preferences",
    response_model=UserResponse,
)
async def update_preferences(
    data: UserPreferencesUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
) -> UserResponse:
    return await update_current_user_preferences(
        request.app.state.database,
        current_user.id,
        data,
    )

@router.put(
    "/notifications",
    response_model=UserResponse,
)
async def update_notifications(
    data: UserNotificationPreferencesUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        get_current_user
    ),
) -> UserResponse:
    return await update_current_user_notifications(
        request.app.state.database,
        current_user.id,
        data,
    )

