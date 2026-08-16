from fastapi import Depends

from app.core.exceptions import AppError
from app.core.permissions import (
    Permission,
    has_permission,
)
from app.dependencies.auth import get_current_user
from app.schemas.user import UserResponse


def require_permission(
    permission: Permission,
):
    async def permission_dependency(
        current_user: UserResponse = Depends(
            get_current_user
        ),
    ) -> UserResponse:

        if not has_permission(
            current_user.role,
            permission,
        ):
            raise AppError(
                "You do not have permission "
                "to perform this action.",
                code="FORBIDDEN",
                status_code=403,
            )

        return current_user

    return permission_dependency