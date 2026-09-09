from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
)

from fastapi.responses import Response

from app.dependencies.auth import get_current_user
from app.schemas.notification import UserNotificationPreferencesUpdate
from app.schemas.user import (
    UserPreferencesUpdate,
    UserProfileUpdate,
    UserResponse,
)
from app.services.image_uploads import read_image_upload
from app.services.users import (
    current_user_avatar,
    delete_current_user_avatar,
    save_current_user_avatar,
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


@router.get("/avatar", include_in_schema=False)
async def get_avatar(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
):
    avatar = await current_user_avatar(request.app.state.database, current_user.id)
    if avatar is None:
        raise HTTPException(status_code=404)
    content_type, data = avatar
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.put("/avatar", response_model=UserResponse)
async def put_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    content_type, data = await read_image_upload(file)
    return await save_current_user_avatar(
        request.app.state.database,
        current_user.id,
        content_type=content_type,
        data=data,
    )


@router.delete("/avatar", response_model=UserResponse)
async def remove_avatar(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    return await delete_current_user_avatar(
        request.app.state.database,
        current_user.id,
    )

