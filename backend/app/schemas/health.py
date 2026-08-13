from typing import Literal

from pydantic import BaseModel


HealthStatus = Literal[
    "healthy",
    "unhealthy",
]


class HealthResponse(BaseModel):
    api: Literal["healthy"] = "healthy"
    mongodb: HealthStatus

    environment: str
    version: str


class ReadinessResponse(BaseModel):
    ready: bool
    mongodb: HealthStatus