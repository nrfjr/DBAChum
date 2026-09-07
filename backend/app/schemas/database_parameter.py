from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DatabaseParameterItem(BaseModel):
    name: str
    value: str | None = None
    display_value: str | None = None
    default_value: str | None = None
    runtime_value: str | None = None
    configured_value: str | None = None
    dynamic: bool | None = None
    session_modifiable: bool | None = None
    system_modifiable: str | None = None
    advanced: bool | None = None
    description: str | None = None
    source: str | None = None


class DatabaseParametersResponse(BaseModel):
    connection_id: str
    engine: str
    scope: Literal["database", "instance", "server"] = "instance"
    generation: str | None = None
    available: bool = True
    items: list[DatabaseParameterItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime
