from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.database_connection import DatabaseEngine


class JobOperation(str, Enum):
    RUN = "run"
    ENABLE = "enable"
    DISABLE = "disable"


class DatabaseJobItem(BaseModel):
    id: str
    name: str
    owner: str | None = None
    enabled: bool | None = None
    status: str | None = None
    schedule: str | None = None
    last_run: datetime | str | None = None
    next_run: datetime | str | None = None
    job_type: str | None = None
    detail: str | None = None
    can_run: bool = False
    can_enable_disable: bool = False


class DatabaseJobsResponse(BaseModel):
    connection_id: str
    engine: DatabaseEngine
    available: bool = True
    items: list[DatabaseJobItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime


class JobOperationRequest(BaseModel):
    action: JobOperation
    job_id: str = Field(min_length=1, max_length=512)
    request_reference: str | None = Field(default=None, max_length=100)
