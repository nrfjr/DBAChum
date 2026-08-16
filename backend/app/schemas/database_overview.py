from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.database_connection import DatabaseEngine


DatabaseMonitoringStatus = Literal[
    "online",
    "limited",
    "unreachable",
    "disabled",
]


class DatabaseOverviewResponse(BaseModel):
    connection_id: str
    engine: DatabaseEngine

    status: DatabaseMonitoringStatus

    response_time_ms: float | None = None

    active: int | None = None
    connections: int | None = None
    blocked: int | None = None
    uptime_seconds: int | None = None

    database_name: str | None = None
    container_name: str | None = None
    service_name: str | None = None
    instance_name: str | None = None
    version: str | None = None

    checked_at: datetime

    warnings: list[str] = Field(default_factory=list)
    error: str | None = None