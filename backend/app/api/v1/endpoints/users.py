from fastapi import (
    APIRouter,
    Depends,
    Request,
    Response,
    status,
)

from app.core.permissions import Permission
from app.dependencies.permissions import (
    require_permission,
)
from app.schemas.user import (
    UserCreate,
    UserPasswordUpdate,
    UserResponse,
    UserUpdate,
)
from app.services.users import (
    create_managed_user,
    delete_managed_user,
    list_users,
    reset_managed_user_password,
    update_managed_user,
)


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)

@router.get(
    "",
    response_model=list[UserResponse],
)
async def get_users(
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(
            Permission.USER_MANAGE
        )
    ),
):
    return await list_users(
        request.app.state.database
    )
    
@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_endpoint(
    data: UserCreate,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(
            Permission.USER_MANAGE
        )
    ),
):
    return await create_managed_user(
        request.app.state.database,
        data,
    )

@router.put(
    "/{user_id}",
    response_model=UserResponse,
)
async def update_user_endpoint(
    user_id: str,
    data: UserUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(
            Permission.USER_MANAGE
        )
    ),
):
    return await update_managed_user(
        request.app.state.database,
        user_id,
        data,
        current_user.id,
    )

@router.put(
    "/{user_id}/password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_user_password_endpoint(
    user_id: str,
    data: UserPasswordUpdate,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(
            Permission.USER_MANAGE
        )
    ),
):
    await reset_managed_user_password(
        request.app.state.database,
        user_id,
        data,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_endpoint(
    user_id: str,
    request: Request,
    current_user: UserResponse = Depends(
        require_permission(
            Permission.USER_MANAGE
        )
    ),
):
    await delete_managed_user(
        request.app.state.database,
        user_id,
        current_user.id,
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT
    )