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
    oracle_auth_mode: Literal["normal", "sysdba"] | None = None

    # SQL Server can use the modern Microsoft Python provider or an
    # explicitly isolated ODBC path for legacy instances such as 2000.
    sqlserver_provider: Literal["auto", "mssql_python", "pyodbc"] | None = None
    sqlserver_driver: str | None = Field(default=None, max_length=128)
    sqlserver_encrypt: Literal["auto", "yes", "no"] | None = None
    
    server_ids: list[str] = Field(default_factory=list,max_length=16,)

    # Whether DBAChum may use this connection for manual/admin operations
    # such as provisioning and metadata discovery.
    active: bool = True

    # Whether the connection appears in the Databases workspace and is
    # collected by the background monitoring worker.
    monitor_enabled: bool | None = None

    # Legacy compatibility alias. Older DBAChum builds used `enabled` for
    # the UI label "Monitor this connection". It is kept on the API during
    # the transition and mirrors monitor_enabled.
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

        if self.monitor_enabled is None:
            self.monitor_enabled = self.enabled

        # Keep the legacy field synchronized so old clients/data readers still
        # interpret it as the monitoring flag rather than account usability.
        self.enabled = self.monitor_enabled

        if self.engine == DatabaseEngine.ORACLE:
            if not self.oracle_identifier_type or not self.oracle_identifier:
                raise ValueError(
                    "Oracle connections require a service name or SID."
                )

            self.oracle_auth_mode = (
                self.oracle_auth_mode or "normal"
            )
        else:
            self.oracle_identifier_type = None
            self.oracle_identifier = None
            self.oracle_auth_mode = None

        if self.engine == DatabaseEngine.SQLSERVER:
            self.sqlserver_provider = self.sqlserver_provider or "auto"
            self.sqlserver_encrypt = self.sqlserver_encrypt or "auto"
            if self.sqlserver_driver is not None:
                self.sqlserver_driver = self.sqlserver_driver.strip() or None
        else:
            self.sqlserver_provider = None
            self.sqlserver_driver = None
            self.sqlserver_encrypt = None

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
    oracle_auth_mode: Literal["normal", "sysdba"] | None = None

    database_edition: str | None = None
    sqlserver_generation: str | None = None
    sqlserver_provider: str | None = None
    sqlserver_driver: str | None = None

    # Generic MySQL-family identity returned by connection tests.
    database_product: str | None = None
    database_generation: str | None = None
    version_comment: str | None = None
    server_hostname: str | None = None
    server_port: int | None = None

    capabilities: dict[str, bool] | None = None

