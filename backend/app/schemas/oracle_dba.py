from datetime import datetime

from pydantic import BaseModel, Field


class OracleSessionItem(BaseModel):
    sid: int
    serial_number: int

    username: str | None = None
    status: str

    os_user: str | None = None
    machine: str | None = None
    program: str | None = None
    module: str | None = None

    sql_id: str | None = None
    sql_exec_start: datetime | None = None

    event: str | None = None
    wait_class: str | None = None

    blocking_instance: int | None = None
    blocking_session: int | None = None

    state_seconds: int

    logon_time: datetime | None = None


class OracleSessionsResponse(BaseModel):
    available: bool = True

    total: int = 0
    active: int = 0
    blocked: int = 0
    long_running: int = 0

    long_running_threshold_seconds: int = 60

    items: list[OracleSessionItem] = Field(
        default_factory=list
    )

    warning: str | None = None
    checked_at: datetime


class OracleTablespaceItem(BaseModel):
    name: str
    contents: str
    status: str

    used_bytes: int
    capacity_bytes: int

    used_percent: float


class OracleFraSummary(BaseModel):
    destination: str | None = None

    limit_bytes: int
    used_bytes: int
    reclaimable_bytes: int

    number_of_files: int

    used_percent: float | None = None


class OracleStorageResponse(BaseModel):
    tablespaces_available: bool = True
    fra_available: bool = True

    tablespaces: list[OracleTablespaceItem] = Field(
        default_factory=list
    )

    fra: OracleFraSummary | None = None

    warnings: list[str] = Field(
        default_factory=list
    )

    checked_at: datetime


class OracleActiveSqlItem(BaseModel):
    sid: int
    serial_number: int

    username: str | None = None

    sql_id: str
    sql_exec_start: datetime | None = None

    active_seconds: int

    module: str | None = None
    machine: str | None = None

    event: str | None = None
    wait_class: str | None = None

    sql_text: str | None = None


class OracleActivityResponse(BaseModel):
    available: bool = True

    items: list[OracleActiveSqlItem] = Field(
        default_factory=list
    )

    warning: str | None = None
    checked_at: datetime