from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

class UserRole(str, Enum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"

class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

class UserCreate(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=64,
    )

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.strip().lower()

        if len(normalized) < 3:
            raise ValueError(
                "Username must be at least 3 characters."
            )

        return normalized

    password: str = Field(
        min_length=12,
        max_length=128,
    )

    role: UserRole = UserRole.VIEWER

    is_active: bool = True


class UserUpdate(BaseModel):
    role: UserRole
    is_active: bool


class UserPasswordUpdate(BaseModel):
    password: str = Field(
        min_length=12,
        max_length=128,
    )