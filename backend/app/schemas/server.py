from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ServerOsFamily(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    AIX = "aix"
    UNIX = "unix"
    OTHER = "other"


class ServerType(str, Enum):
    DATABASE = "database"
    APPLICATION = "application"
    UTILITY = "utility"
    OTHER = "other"


class ServerBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    hostname: str = Field(min_length=1, max_length=255)
    ip_address: str | None = Field(default=None, max_length=64)

    server_type: ServerType = ServerType.DATABASE
    os_family: ServerOsFamily
    os_version: str | None = Field(default=None, max_length=128)

    environment: str | None = Field(default=None, max_length=64)
    owner: str | None = Field(default=None, max_length=128)

    tags: list[str] = Field(default_factory=list, max_length=32)
    notes: str | None = Field(default=None, max_length=2000)

    ssh_profile_id: str | None = Field(default=None, max_length=64)
    database_connection_ids: list[str] = Field(default_factory=list, max_length=100)

    enabled: bool = True

    @field_validator(
        "name",
        "hostname",
        "ip_address",
        "os_version",
        "environment",
        "owner",
        "notes",
        "ssh_profile_id",
        mode="before",
    )
    @classmethod
    def clean_strings(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        return value or None

    @field_validator("database_connection_ids")
    @classmethod
    def validate_database_connection_ids(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("Duplicate database relationships are not allowed.")
        return cleaned


class ServerCreate(ServerBase):
    pass


class ServerUpdate(ServerBase):
    pass


class ServerResponse(ServerBase):
    id: str
    database_count: int = 0
    ssh_profile_name: str | None = None
    created_at: datetime
    updated_at: datetime
