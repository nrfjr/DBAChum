from datetime import datetime

from pydantic import BaseModel, Field


class MySqlSessionItem(BaseModel):
    connection_id: int

    user: str | None = None
    host: str | None = None
    database: str | None = None

    command: str | None = None
    state: str | None = None

    elapsed_seconds: int

    sql_text: str | None = None


class MySqlSessionsResponse(BaseModel):
    available: bool = True

    total: int | None = None
    active: int | None = None
    blocked: int | None = None
    long_running: int | None = None

    long_running_threshold_seconds: int = 60

    items: list[MySqlSessionItem] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(default_factory=list)

    checked_at: datetime


class MySqlTableStorageItem(BaseModel):
    table_name: str

    data_bytes: int
    index_bytes: int
    total_bytes: int

    rows_estimate: int | None = None


class MySqlStorageResponse(BaseModel):
    available: bool = True

    database_name: str | None = None

    data_bytes: int
    index_bytes: int
    total_bytes: int

    tables: list[MySqlTableStorageItem] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(default_factory=list)

    checked_at: datetime


class MySqlActivityItem(BaseModel):
    connection_id: int

    user: str | None = None
    host: str | None = None
    database: str | None = None

    elapsed_seconds: int

    state: str | None = None
    sql_text: str | None = None


class MySqlActivityResponse(BaseModel):
    available: bool = True

    items: list[MySqlActivityItem] = Field(
        default_factory=list
    )

    warning: str | None = None

    checked_at: datetime