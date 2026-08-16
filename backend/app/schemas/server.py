from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class ServerOsFamily(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    AIX = "aix"
    UNIX = "unix"
    OTHER = "other"


class ServerBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=100,
    )

    hostname: str = Field(
        min_length=1,
        max_length=255,
    )

    ip_address: str | None = Field(
        default=None,
        max_length=64,
    )

    os_family: ServerOsFamily
    os_version: str | None = Field(
        default=None,
        max_length=128,
    )

    environment: str | None = Field(
        default=None,
        max_length=64,
    )

    owner: str | None = Field(
        default=None,
        max_length=128,
    )

    tags: list[str] = Field(
        default_factory=list,
        max_length=32,
    )

    notes: str | None = Field(
        default=None,
        max_length=2000,
    )

    enabled: bool = True

    @field_validator(
        "name",
        "hostname",
        "ip_address",
        "os_version",
        "environment",
        "owner",
        "notes",
        mode="before",
    )
    @classmethod
    def clean_strings(cls, value):
        if not isinstance(value, str):
            return value

        value = value.strip()

        return value or None


class ServerCreate(ServerBase):
    pass


class ServerUpdate(ServerBase):
    pass


class ServerResponse(ServerBase):
    id: str
    database_count: int = 0

    created_at: datetime
    updated_at: datetime