from typing import Literal

from pydantic import BaseModel, Field, model_validator


PageSize = Literal[10, 25, 50, 100]


class GeneralSettingsUpdate(BaseModel):
    installation_name: str = Field(min_length=1, max_length=80)
    default_page_size: PageSize = 10
    default_analytics_months: int = Field(default=12, ge=1, le=60)


class MonitoringSettingsUpdate(BaseModel):
    enabled: bool = True
    database_interval_seconds: int = Field(default=30, ge=10, le=300)
    server_interval_seconds: int = Field(default=60, ge=30, le=600)
    storage_interval_seconds: int = Field(default=300, ge=60, le=3600)
    analytics_snapshot_interval_seconds: int = Field(default=21600, ge=900, le=86400)
    target_timeout_seconds: int = Field(default=45, ge=10, le=300)
    concurrency: int = Field(default=5, ge=1, le=20)
    stale_threshold_seconds: int = Field(default=30, ge=20, le=300)

    @model_validator(mode="after")
    def validate_cadence(self):
        # The collector loop is driven by the database interval. Slower
        # activities can be scheduled independently, but they cannot run more
        # frequently than the loop that wakes the collector.
        if self.server_interval_seconds < self.database_interval_seconds:
            raise ValueError("Server interval must be greater than or equal to the database interval.")
        if self.storage_interval_seconds < self.database_interval_seconds:
            raise ValueError("Storage interval must be greater than or equal to the database interval.")
        return self


class DataSettingsUpdate(BaseModel):
    analytics_retention_days: int = Field(default=730, ge=30, le=3650)
    action_audit_retention_days: int = Field(default=365, ge=30, le=3650)
    terminal_audit_retention_days: int = Field(default=365, ge=30, le=3650)
    provisioning_history_retention_days: int = Field(default=365, ge=30, le=3650)


class CleanupRequest(BaseModel):
    apply_retention: bool = True
    remove_orphaned_analytics: bool = True
    reconcile_stale_terminal_sessions: bool = True
