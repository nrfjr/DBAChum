from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class TopSqlItem(BaseModel):
    key: str
    sql_text: str | None = None
    normalized_sql: bool = False
    schema_name: str | None = None
    executions: int | None = None
    elapsed_seconds: float | None = None
    cpu_seconds: float | None = None
    logical_reads: int | None = None
    physical_reads: int | None = None
    rows_processed: int | None = None
    last_active_at: datetime | None = None
    sql_id: str | None = None
    child_number: int | None = None
    plan_hash_value: int | None = None
    plan_handle: str | None = None
    sql_handle: str | None = None
    statement_start_offset: int | None = None
    statement_end_offset: int | None = None
    digest: str | None = None
    rows_examined: int | None = None
    rows_sent: int | None = None
    no_index_used: int | None = None
    no_good_index_used: int | None = None
    temp_disk_tables: int | None = None
    diagnostics: list[str] = Field(default_factory=list)


class TopSqlResponse(BaseModel):
    connection_id: str
    engine: str
    source: str
    available: bool = True
    items: list[TopSqlItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime


class SqlPlanRequest(BaseModel):
    sql_id: str | None = Field(default=None, max_length=32)
    child_number: int | None = Field(default=None, ge=0)
    plan_handle: str | None = Field(default=None, max_length=256)
    sql_text: str | None = Field(default=None, max_length=200_000)

    @model_validator(mode="after")
    def validate_selector(self):
        if not any((self.sql_id, self.plan_handle, self.sql_text)):
            raise ValueError("A SQL identifier or SQL text is required.")
        return self


class SqlPlanStep(BaseModel):
    id: int | None = None
    parent_id: int | None = None
    operation: str | None = None
    options: str | None = None
    object_owner: str | None = None
    object_name: str | None = None
    cost: float | None = None
    cardinality: float | None = None
    bytes: float | None = None
    access_predicates: str | None = None
    filter_predicates: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SqlPlanResponse(BaseModel):
    connection_id: str
    engine: str
    source: str
    available: bool = True
    plan_text: str | None = None
    steps: list[SqlPlanStep] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime
