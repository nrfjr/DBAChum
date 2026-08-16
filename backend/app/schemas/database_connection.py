from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DatabaseEngine(str, Enum):
    ORACLE = "oracle"
    SQLSERVER = "sqlserver"
    MYSQL = "mysql"


class DatabaseConnectionBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    engine: DatabaseEngine

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)

    username: str = Field(min_length=1, max_length=128)

    database: str | None = Field(default=None, max_length=128)

    oracle_identifier_type: Literal["service_name", "sid"] | None = None
    oracle_identifier: str | None = Field(default=None, max_length=128)
    
    server_ids: list[str] = Field(default_factory=list,max_length=16,)

    enabled: bool = True

    @model_validator(mode="after")
    def validate_connection(self):
        self.name = self.name.strip()
        self.host = self.host.strip()
        self.username = self.username.strip()

        if not self.name:
            raise ValueError("Connection name is required.")

        if not self.host:
            raise ValueError("Host is required.")

        if not self.username:
            raise ValueError("Username is required.")

        if self.database is not None:
            self.database = self.database.strip() or None

        if self.oracle_identifier is not None:
            self.oracle_identifier = self.oracle_identifier.strip() or None

        if self.engine == DatabaseEngine.ORACLE:
            if not self.oracle_identifier_type or not self.oracle_identifier:
                raise ValueError(
                    "Oracle connections require a service name or SID."
                )
        else:
            self.oracle_identifier_type = None
            self.oracle_identifier = None

        return self
    


class DatabaseConnectionCreate(DatabaseConnectionBase):
    password: str = Field(min_length=1, max_length=512)


class DatabaseConnectionUpdate(DatabaseConnectionBase):
    password: str | None = Field(default=None, max_length=512)


class DatabaseConnectionResponse(DatabaseConnectionBase):
    id: str
    has_password: bool
    created_at: datetime
    updated_at: datetime

class DatabaseConnectionTestResponse(BaseModel):
    success: bool
    engine: DatabaseEngine
    message: str

    database_name: str | None = None
    service_name: str | None = None
    connected_user: str | None = None
    database_version: str | None = None

