from datetime import datetime

from pydantic import BaseModel, Field


class SqlServerSessionItem(BaseModel):
    session_id: int
    login_name: str | None = None
    status: str | None = None
    host_name: str | None = None
    program_name: str | None = None

    request_status: str | None = None
    command: str | None = None
    request_start_time: datetime | None = None

    elapsed_ms: int | None = None
    cpu_ms: int | None = None

    wait_type: str | None = None
    blocking_session_id: int | None = None

    sql_text: str | None = None


class SqlServerSessionsResponse(BaseModel):
    available: bool = True

    total: int | None = None
    active: int | None = None
    blocked: int | None = None
    long_running: int | None = None

    long_running_threshold_seconds: int = 60

    items: list[SqlServerSessionItem] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(default_factory=list)

    checked_at: datetime


class SqlServerFileItem(BaseModel):
    name: str
    physical_name: str | None = None
    file_type: str

    allocated_bytes: int
    used_bytes: int | None = None
    free_bytes: int | None = None

    used_percent: float | None = None


class SqlServerStorageResponse(BaseModel):
    available: bool = True

    database_name: str | None = None
    allocated_bytes: int | None = None
    used_bytes: int | None = None

    files: list[SqlServerFileItem] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(default_factory=list)

    checked_at: datetime


class SqlServerActivityItem(BaseModel):
    session_id: int
    login_name: str | None = None

    status: str | None = None
    command: str | None = None

    elapsed_ms: int
    cpu_ms: int | None = None

    wait_type: str | None = None
    wait_ms: int | None = None

    blocking_session_id: int | None = None

    database_name: str | None = None
    sql_text: str | None = None


class SqlServerActivityResponse(BaseModel):
    available: bool = True

    items: list[SqlServerActivityItem] = Field(
        default_factory=list
    )

    warning: str | None = None

    checked_at: datetime

class SqlServerLoginItem(BaseModel):
    name: str
    principal_type: str
    disabled: bool = False
    default_database: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)


class SqlServerDatabaseUserItem(BaseModel):
    name: str
    principal_type: str
    login_name: str | None = None
    default_schema: str | None = None
    authentication_type: str | None = None
    orphaned: bool = False
    created_at: datetime | None = None
    modified_at: datetime | None = None
    roles: list[str] = Field(default_factory=list)


class SqlServerRoleMembershipItem(BaseModel):
    principal: str
    role: str
    source: str


class SqlServerPermissionItem(BaseModel):
    principal: str
    state: str
    permission: str
    scope: str
    class_name: str | None = None
    securable: str | None = None
    grantor: str | None = None


class SqlServerElevatedFinding(BaseModel):
    principal: str
    severity: str
    source: str
    detail: str


class SqlServerSecurityResponse(BaseModel):
    available: bool = True
    database_name: str | None = None
    generation: str | None = None

    login_count: int = 0
    database_user_count: int = 0
    disabled_login_count: int = 0
    orphaned_user_count: int = 0

    logins: list[SqlServerLoginItem] = Field(default_factory=list)
    database_users: list[SqlServerDatabaseUserItem] = Field(default_factory=list)
    server_roles: list[SqlServerRoleMembershipItem] = Field(default_factory=list)
    database_roles: list[SqlServerRoleMembershipItem] = Field(default_factory=list)
    server_permissions: list[SqlServerPermissionItem] = Field(default_factory=list)
    database_permissions: list[SqlServerPermissionItem] = Field(default_factory=list)
    elevated_findings: list[SqlServerElevatedFinding] = Field(default_factory=list)

    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime
