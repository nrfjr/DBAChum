from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Request,
    Response,
)

from app.core.config import settings
from app.core.exceptions import AppError
from app.dependencies.auth import (
    get_current_user,
)
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
)
from app.schemas.user import UserResponse
from app.services.auth import (
    authenticate_user,
    create_session,
    delete_session,
)
from app.services.users import (
    user_to_response,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=LoginResponse,
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> LoginResponse:
    database = request.app.state.database

    user = await authenticate_user(
        database,
        payload.username,
        payload.password,
    )

    if user is None:
        raise AppError(
            "Invalid username or password.",
            code="INVALID_CREDENTIALS",
            status_code=401,
        )

    raw_token, _ = await create_session(
        database,
        user,
    )

    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,

        max_age=(
            settings.session_hours
            * 60
            * 60
        ),

        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",

        path="/",
    )

    return LoginResponse(
        user=user_to_response(user)
    )


@router.post(
    "/logout",
    response_model=LogoutResponse,
)
async def logout(
    request: Request,
    response: Response,

    session_token: str | None = Cookie(
        default=None,
        alias=settings.session_cookie_name,
    ),
) -> LogoutResponse:
    if session_token is not None:
        await delete_session(
            request.app.state.database,
            session_token,
        )

    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )

    return LogoutResponse(
        message="Logged out successfully."
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
async def me(
    current_user: UserResponse = Depends(
        get_current_user
    ),
) -> UserResponse:
    return current_user