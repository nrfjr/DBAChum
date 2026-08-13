from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: str

    username: str
    display_name: str

    role: str
    is_active: bool

    created_at: datetime