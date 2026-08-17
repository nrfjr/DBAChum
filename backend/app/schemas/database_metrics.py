from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.database_connection import (
    DatabaseEngine,
)
from app.schemas.database_overview import (
    DatabaseMonitoringStatus,
)


class DatabaseMetricSampleResponse(BaseModel):
    collected_at: datetime
    checked_at: datetime | None = None

    status: DatabaseMonitoringStatus

    response_time_ms: float | None = None

    active: int | None = None
    connections: int | None = None
    blocked: int | None = None

    uptime_seconds: int | None = None

    warnings: list[str] = Field(default_factory=list)

    error: str | None = None


class DatabaseMetricHistoryResponse(BaseModel):
    connection_id: str
    engine: DatabaseEngine
    from_at: datetime
    to_at: datetime
    sample_interval_seconds: int
    count: int
    items: list[DatabaseMetricSampleResponse] = Field(default_factory=list)
