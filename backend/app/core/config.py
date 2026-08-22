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

    metrics_collector_enabled: bool = True
    metrics_collector_interval_seconds: int = Field(
        default=60,
        ge=10,
    )
    metrics_retention_days: int = Field(
        default=30,
        ge=1,
    )

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

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
