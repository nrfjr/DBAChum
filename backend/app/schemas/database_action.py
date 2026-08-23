from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DatabaseActionRisk(str, Enum):
    SAFE = "safe"
    SENSITIVE = "sensitive"
    DANGEROUS = "dangerous"


class DatabaseActionStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class DatabaseActionAuditResponse(BaseModel):
    id: str
    connection_id: str
    engine: str

    action: str
    target: str | None = None

    risk: DatabaseActionRisk
    status: DatabaseActionStatus

    operator_user_id: str
    operator_username: str

    request_reference: str | None = None

    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    details: dict[str, Any] = Field(
        default_factory=dict
    )

    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
