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
    edition: str | None = None
    product_level: str | None = None
    generation: str | None = None
    connection_provider: str | None = None
    connection_driver: str | None = None
    connection_encrypt: str | None = None

    database_product: str | None = None
    version_comment: str | None = None
    server_hostname: str | None = None
    server_port: int | None = None
    database_count: int | None = None
    max_connections: int | None = None
    questions: int | None = None
    slow_queries: int | None = None
    data_directory: str | None = None
    performance_schema_enabled: bool | None = None

    capabilities: dict[str, bool] | None = None

    checked_at: datetime

    warnings: list[str] = Field(default_factory=list)
    error: str | None = None