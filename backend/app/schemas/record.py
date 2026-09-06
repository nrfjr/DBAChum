from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.schemas.database_connection import DatabaseEngine


class RecordType(str, Enum):
    DATABASE = "database"
    SERVER = "server"
    APPLICATION = "application"
    CREDENTIAL = "credential"
    URL = "url"
    OTHER = "other"


class RecordStatus(str, Enum):
    ACTIVE = "active"
    STANDBY = "standby"
    DISABLED = "disabled"
    RETIRED = "retired"
    UNKNOWN = "unknown"


class RecordCustomField(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(default="", max_length=1000)

    @field_validator("key", "value", mode="before")
    @classmethod
    def clean_custom_field(cls, value):
        if not isinstance(value, str):
            return value
        return value.strip()


class RecordBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    record_type: RecordType = RecordType.DATABASE
    status: RecordStatus = RecordStatus.ACTIVE
    engine: DatabaseEngine | None = None

    hostname: str | None = Field(default=None, max_length=255)
    ip_address: str | None = Field(default=None, max_length=64)
    port: int | None = Field(default=None, ge=1, le=65535)
    environment: str | None = Field(default=None, max_length=80)
    version: str | None = Field(default=None, max_length=160)
    username: str | None = Field(default=None, max_length=160)
    application: str | None = Field(default=None, max_length=160)
    owner: str | None = Field(default=None, max_length=160)
    url: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=5000)

    tags: list[str] = Field(default_factory=list, max_length=32)
    custom_fields: list[RecordCustomField] = Field(default_factory=list, max_length=32)

    connection_id: str | None = Field(default=None, max_length=64)
    server_id: str | None = Field(default=None, max_length=64)

    @field_validator(
        "name",
        "hostname",
        "ip_address",
        "environment",
        "version",
        "username",
        "application",
        "owner",
        "url",
        "notes",
        "connection_id",
        "server_id",
        mode="before",
    )
    @classmethod
    def clean_strings(cls, value):
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        return cleaned or None

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str | None) -> str:
        if not value:
            raise ValueError("Record name is required.")
        return value

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            tag = str(item).strip()
            key = tag.lower()
            if not tag or key in seen:
                continue
            seen.add(key)
            result.append(tag)
        return result

    @field_validator("custom_fields")
    @classmethod
    def unique_custom_fields(
        cls,
        value: list[RecordCustomField],
    ) -> list[RecordCustomField]:
        seen: set[str] = set()
        for item in value:
            key = item.key.strip().lower()
            if key in seen:
                raise ValueError(
                    f'Duplicate custom field "{item.key}" is not allowed.'
                )
            seen.add(key)
        return value


class RecordCreate(RecordBase):
    password: str | None = Field(default=None, max_length=512)


class RecordUpdate(RecordBase):
    password: str | None = Field(default=None, max_length=512)


class RecordResponse(RecordBase):
    id: str
    has_password: bool = False
    connection_name: str | None = None
    server_name: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class RecordSecretResponse(BaseModel):
    password: str
