from pydantic import (
    BaseModel,
    Field,
)

from app.schemas.user import UserResponse


class LoginRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=64,
    )

    password: str = Field(
        min_length=8,
        max_length=256,
    )


class LoginResponse(BaseModel):
    user: UserResponse


class LogoutResponse(BaseModel):
    message: str