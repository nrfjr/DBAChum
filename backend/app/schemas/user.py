from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from pydantic import BaseModel

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

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    role: UserRole = UserRole.VIEWER

    is_active: bool = True


class UserUpdate(BaseModel):
    role: UserRole
    enabled: bool


class UserPasswordUpdate(BaseModel):
    password: str = Field(
        min_length=8,
        max_length=128,
    )