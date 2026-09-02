from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.database_connection import DatabaseEngine


BackupStatus = Literal[
    "successful",
    "warning",
    "failed",
    "running",
    "unknown",
]

BackupKind = Literal[
    "full",
    "differential",
    "incremental",
    "log",
    "archive_log",
    "file",
    "partial",
    "controlfile",
    "spfile",
    "other",
]

BackupWindow = Literal["today", "3d", "7d", "custom"]
BackupDetailValue = str | int | float | bool | None


class DatabaseBackupItem(BaseModel):
    backup_id: str
    database_name: str | None = None
    kind: BackupKind
    native_type: str | None = None
    status: BackupStatus = "unknown"
    native_status: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    input_bytes: int | None = None
    output_bytes: int | None = None
    backup_size_bytes: int | None = None
    destinations: list[str] = Field(default_factory=list)
    device_type: str | None = None
    label: str | None = None
    owner: str | None = None
    details: dict[str, BackupDetailValue] = Field(default_factory=dict)


class DatabaseBackupTargetSummary(BaseModel):
    database_name: str
    recovery_model: str | None = None
    last_full: DatabaseBackupItem | None = None
    last_differential: DatabaseBackupItem | None = None
    last_incremental: DatabaseBackupItem | None = None
    last_log: DatabaseBackupItem | None = None


class DatabaseBackupResponse(BaseModel):
    connection_id: str
    engine: DatabaseEngine
    available: bool = True
    source: str
    scope: Literal["database", "instance", "external"] = "database"
    database_name: str | None = None
    generation: str | None = None
    selected_window: BackupWindow = "today"
    custom_start_date: date | None = None
    custom_end_date: date | None = None
    latest_backup: DatabaseBackupItem | None = None
    summaries: list[DatabaseBackupTargetSummary] = Field(default_factory=list)
    items: list[DatabaseBackupItem] = Field(default_factory=list)
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    checked_at: datetime
