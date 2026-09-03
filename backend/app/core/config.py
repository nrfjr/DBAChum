from functools import lru_cache

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DBAChum API"
    app_version: str = "2.0.0"
    environment: str = "development"
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"
    api_docs_enabled: bool = True

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "dbachum"

    session_cookie_name: str = "dbachum_session"
    session_hours: int = Field(
        default=12,
        ge=1,
        le=168,
    )
    cookie_secure: bool = False

    connection_encryption_key: str

    oracle_driver_mode: str = "thin"
    oracle_client_lib_dir: str | None = None

    # Phase 6A collector settings. The collector runs as a separate process
    # (python -m app.collector), not inside the FastAPI web process.
    metrics_collector_enabled: bool = True
    metrics_collector_interval_seconds: int = Field(
        default=30,
        ge=10,
        le=300,
    )
    server_metrics_interval_seconds: int = Field(
        default=60,
        ge=30,
        le=600,
    )
    oracle_storage_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
    )
    sqlserver_health_interval_seconds: int = Field(
        default=60,
        ge=30,
        le=3600,
    )
    mysql_storage_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
    )
    metrics_collector_concurrency: int = Field(
        default=5,
        ge=1,
        le=20,
    )
    metrics_target_timeout_seconds: int = Field(
        default=45,
        ge=10,
        le=300,
    )
    # DBAChum intentionally retains telemetry for only one rolling day.
    # Keeping this fixed prevents the product from drifting into a long-term
    # telemetry warehouse.
    metrics_retention_hours: int = Field(
        default=24,
        ge=24,
        le=24,
    )

    # Phase 6D alert thresholds. Alerts are intentionally short-horizon and
    # collector-backed; they do not extend telemetry beyond the 24-hour cap.
    alert_collector_stale_seconds: int = Field(default=30, ge=20, le=300)
    alert_active_sessions_warning: int = Field(default=100, ge=0, le=100000)
    alert_active_sessions_critical: int = Field(default=200, ge=0, le=100000)
    alert_tablespace_warning_percent: float = Field(default=85.0, ge=1, le=100)
    alert_tablespace_critical_percent: float = Field(default=95.0, ge=1, le=100)
    alert_fra_warning_percent: float = Field(default=85.0, ge=1, le=100)
    alert_fra_critical_percent: float = Field(default=95.0, ge=1, le=100)
    alert_filesystem_warning_percent: float = Field(default=80.0, ge=1, le=100)
    alert_filesystem_critical_percent: float = Field(default=90.0, ge=1, le=100)
    alert_server_cpu_warning_percent: float = Field(default=90.0, ge=1, le=100)
    alert_server_cpu_critical_percent: float = Field(default=97.0, ge=1, le=100)
    alert_server_memory_warning_percent: float = Field(default=90.0, ge=1, le=100)
    alert_server_memory_critical_percent: float = Field(default=97.0, ge=1, le=100)

    # SQL Server operational alerts. Long-running requests stay informational
    # until explicitly enabled because acceptable duration is workload-specific.
    alert_sqlserver_log_warning_percent: float = Field(default=80.0, ge=1, le=100)
    alert_sqlserver_log_critical_percent: float = Field(default=90.0, ge=1, le=100)
    alert_sqlserver_tempdb_warning_percent: float = Field(default=90.0, ge=1, le=100)
    alert_sqlserver_tempdb_critical_percent: float = Field(default=98.0, ge=1, le=100)
    alert_sqlserver_long_running_seconds: int = Field(default=0, ge=0, le=604800)

    # MySQL/MariaDB operational alerts. Connection saturation has a stable
    # meaning across the family. Long-running workload remains opt-in because
    # acceptable execution time is application-specific.
    alert_mysql_connection_warning_percent: float = Field(default=80.0, ge=1, le=100)
    alert_mysql_connection_critical_percent: float = Field(default=90.0, ge=1, le=100)
    alert_mysql_long_running_seconds: int = Field(default=0, ge=0, le=604800)

    trusted_hosts: str = "localhost,127.0.0.1"

    cors_origins: str = (
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "http://localhost:4173,"
        "http://127.0.0.1:4173"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()

        if normalized not in {
            "development",
            "test",
            "production",
        }:
            raise ValueError(
                "ENVIRONMENT must be development, test, or production."
            )

        return normalized


    @field_validator("oracle_driver_mode")
    @classmethod
    def validate_oracle_driver_mode(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip().lower()
        if normalized not in {"thin", "thick"}:
            raise ValueError(
                "ORACLE_DRIVER_MODE must be thin or thick."
            )
        return normalized

    @field_validator("connection_encryption_key")
    @classmethod
    def validate_connection_encryption_key(
        cls,
        value: str,
    ) -> str:
        try:
            Fernet(value.encode("utf-8"))
        except Exception as exc:
            raise ValueError(
                "CONNECTION_ENCRYPTION_KEY must be a valid Fernet key."
            ) from exc

        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def trusted_host_list(self) -> list[str]:
        return [
            host.strip()
            for host in self.trusted_hosts.split(",")
            if host.strip()
        ]

    @model_validator(mode="after")
    def validate_production_security(self):
        if not self.trusted_host_list:
            raise ValueError(
                "TRUSTED_HOSTS must contain at least one host."
            )

        if self.is_production:
            if "*" in self.trusted_host_list:
                raise ValueError(
                    "TRUSTED_HOSTS cannot contain '*' in production."
                )

            if "*" in self.cors_origin_list:
                raise ValueError(
                    "CORS_ORIGINS cannot contain '*' in production."
                )

        threshold_pairs = [
            (self.alert_active_sessions_warning, self.alert_active_sessions_critical, "active sessions"),
            (self.alert_tablespace_warning_percent, self.alert_tablespace_critical_percent, "tablespace"),
            (self.alert_fra_warning_percent, self.alert_fra_critical_percent, "FRA"),
            (self.alert_filesystem_warning_percent, self.alert_filesystem_critical_percent, "filesystem"),
            (self.alert_server_cpu_warning_percent, self.alert_server_cpu_critical_percent, "server CPU"),
            (self.alert_server_memory_warning_percent, self.alert_server_memory_critical_percent, "server memory"),
            (self.alert_sqlserver_log_warning_percent, self.alert_sqlserver_log_critical_percent, "SQL Server transaction log"),
            (self.alert_sqlserver_tempdb_warning_percent, self.alert_sqlserver_tempdb_critical_percent, "SQL Server tempdb"),
            (self.alert_mysql_connection_warning_percent, self.alert_mysql_connection_critical_percent, "MySQL/MariaDB connections"),
        ]
        for warning, critical, label in threshold_pairs:
            if warning > 0 and critical < warning:
                raise ValueError(f"{label} critical alert threshold must be >= warning threshold.")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
