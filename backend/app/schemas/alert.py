from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class AlertSourceType(str, Enum):
    DATABASE = "database"
    SERVER = "server"
    COLLECTOR = "collector"


class AlertResponse(BaseModel):
    id: str
    alert_key: str
    source_type: AlertSourceType
    source_id: str
    source_name: str
    rule_key: str
    severity: AlertSeverity
    status: AlertStatus
    title: str
    message: str
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None = None
    current_value: float | int | str | None = None
    threshold: float | int | str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AlertSummaryResponse(BaseModel):
    active: int = 0
    warning: int = 0
    critical: int = 0
    resolved: int = 0


class AlertClearResponse(BaseModel):
    cleared: bool
    suppressed_until_recovery: bool = False
