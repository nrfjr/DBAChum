from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class SshAuthType(str, Enum):
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"


class SshAccessProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=1, max_length=128)
    port: int = Field(default=22, ge=1, le=65535)
    auth_type: SshAuthType = SshAuthType.PASSWORD
    notes: str | None = Field(default=None, max_length=2000)
    enabled: bool = True

    @field_validator("name", "username", "notes", mode="before")
    @classmethod
    def clean_strings(cls, value):
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        return cleaned or None


class SshAccessProfileCreate(SshAccessProfileBase):
    password: str | None = Field(default=None, max_length=4096)
    private_key: str | None = Field(default=None, max_length=32768)
    passphrase: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_auth_secret(self):
        if self.auth_type == SshAuthType.PASSWORD and not self.password:
            raise ValueError("Password is required for password authentication.")
        if self.auth_type == SshAuthType.PRIVATE_KEY and not self.private_key:
            raise ValueError("Private key is required for private-key authentication.")
        return self


class SshAccessProfileUpdate(SshAccessProfileBase):
    password: str | None = Field(default=None, max_length=4096)
    private_key: str | None = Field(default=None, max_length=32768)
    passphrase: str | None = Field(default=None, max_length=4096)


class SshAccessProfileResponse(SshAccessProfileBase):
    id: str
    has_password: bool = False
    has_private_key: bool = False
    has_passphrase: bool = False
    server_count: int = 0
    created_at: datetime
    updated_at: datetime
