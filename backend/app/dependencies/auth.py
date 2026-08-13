from fastapi import (
    Cookie,
    Request,
)

from app.core.config import settings
from app.core.exceptions import AppError
from app.services.auth import (
    get_user_from_session,
)
from app.services.users import (
    user_to_response,
)


async def get_current_user(
    request: Request,

    session_token: str | None = Cookie(
        default=None,
        alias=settings.session_cookie_name,
    ),
):
    if session_token is None:
        raise AppError(
            "Authentication required.",
            code="AUTH_REQUIRED",
            status_code=401,
        )

    user = await get_user_from_session(
        request.app.state.database,
        session_token,
    )

    if user is None:
        raise AppError(
            "Session is invalid or expired.",
            code="INVALID_SESSION",
            status_code=401,
        )

    return user_to_response(user)