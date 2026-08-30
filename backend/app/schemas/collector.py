from datetime import datetime

from pydantic import BaseModel


class CollectorStatusResponse(BaseModel):
    state: str
    alive: bool
    hostname: str | None = None
    pid: int | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    last_cycle_started_at: datetime | None = None
    last_cycle_completed_at: datetime | None = None
    next_cycle_at: datetime | None = None
    last_cycle_duration_ms: float | None = None
    interval_seconds: int
    server_interval_seconds: int
    retention_hours: int = 24
    database_targets_polled: int = 0
    database_online: int = 0
    database_failed: int = 0
    database_samples_inserted: int = 0
    server_last_polled_at: datetime | None = None
    server_targets_polled: int = 0
    server_online: int = 0
    server_failed: int = 0
    server_samples_inserted: int = 0
    samples_inserted: int = 0
    last_error: str | None = None
