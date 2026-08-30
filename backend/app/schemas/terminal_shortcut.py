from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TerminalShortcutMode(str, Enum):
    EXECUTE = "execute"
    INSERT = "insert"


class TerminalShortcutBase(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    category: str = Field(default="General", min_length=1, max_length=64)
    command: str = Field(min_length=1, max_length=4000)
    mode: TerminalShortcutMode = TerminalShortcutMode.EXECUTE
    server_ids: list[str] = Field(default_factory=list, max_length=100)
    enabled: bool = True
    sort_order: int = Field(default=100, ge=0, le=10000)

    @field_validator("name", "category", "command", mode="before")
    @classmethod
    def clean_text(cls, value):
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("server_ids")
    @classmethod
    def clean_server_ids(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Duplicate server assignments are not allowed.")
        return cleaned


class TerminalShortcutCreate(TerminalShortcutBase):
    pass


class TerminalShortcutUpdate(TerminalShortcutBase):
    pass


class TerminalShortcutResponse(TerminalShortcutBase):
    id: str
    scope_label: str
    created_at: datetime
    updated_at: datetime


class TerminalSessionAuditResponse(BaseModel):
    session_id: str
    operator_user_id: str
    operator_username: str
    server_id: str
    server_name: str
    target: str
    ssh_username: str
    ssh_profile_id: str
    ssh_profile_name: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: float | None = None
    close_reason: str | None = None
    status: str
    input_bytes: int = 0
    output_bytes: int = 0
    shortcut_actions: list[dict] = Field(default_factory=list)
