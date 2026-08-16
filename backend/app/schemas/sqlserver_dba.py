from datetime import datetime

from pydantic import BaseModel, Field


class SqlServerSessionItem(BaseModel):
    session_id: int
    login_name: str | None = None
    status: str | None = None
    host_name: str | None = None
    program_name: str | None = None

    request_status: str | None = None
    command: str | None = None
    request_start_time: datetime | None = None

    elapsed_ms: int | None = None
    cpu_ms: int | None = None

    wait_type: str | None = None
    blocking_session_id: int | None = None

    sql_text: str | None = None


class SqlServerSessionsResponse(BaseModel):
    available: bool = True

    total: int | None = None
    active: int | None = None
    blocked: int | None = None
    long_running: int | None = None

    long_running_threshold_seconds: int = 60

    items: list[SqlServerSessionItem] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(default_factory=list)

    checked_at: datetime


class SqlServerFileItem(BaseModel):
    name: str
    physical_name: str | None = None
    file_type: str

    allocated_bytes: int
    used_bytes: int | None = None
    free_bytes: int | None = None

    used_percent: float | None = None


class SqlServerStorageResponse(BaseModel):
    available: bool = True

    database_name: str | None = None
    allocated_bytes: int | None = None
    used_bytes: int | None = None

    files: list[SqlServerFileItem] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(default_factory=list)

    checked_at: datetime


class SqlServerActivityItem(BaseModel):
    session_id: int
    login_name: str | None = None

    status: str | None = None
    command: str | None = None

    elapsed_ms: int
    cpu_ms: int | None = None

    wait_type: str | None = None
    wait_ms: int | None = None

    blocking_session_id: int | None = None

    database_name: str | None = None
    sql_text: str | None = None


class SqlServerActivityResponse(BaseModel):
    available: bool = True

    items: list[SqlServerActivityItem] = Field(
        default_factory=list
    )

    warning: str | None = None

    checked_at: datetime