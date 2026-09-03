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


class SqlServerDatabaseHealth(BaseModel):
    name: str | None = None
    state: str | None = None
    recovery_model: str | None = None
    user_access: str | None = None
    read_only: bool | None = None
    auto_close: bool | None = None
    auto_shrink: bool | None = None
    log_reuse_wait: str | None = None
    page_verify: str | None = None
    compatibility_level: int | None = None


class SqlServerLogHealth(BaseModel):
    size_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    used_percent: float | None = None
    status_code: int | None = None


class SqlServerWorkloadHealth(BaseModel):
    active: int | None = None
    blocked: int | None = None
    long_running: int | None = None
    longest_request_ms: int | None = None
    long_running_threshold_seconds: int = 300


class SqlServerTempDbFile(BaseModel):
    name: str
    physical_name: str | None = None
    file_type: str
    allocated_bytes: int
    used_bytes: int | None = None
    free_bytes: int | None = None
    used_percent: float | None = None


class SqlServerTempDbHealth(BaseModel):
    allocated_bytes: int | None = None
    used_bytes: int | None = None
    free_bytes: int | None = None
    used_percent: float | None = None
    files: list[SqlServerTempDbFile] = Field(default_factory=list)


class SqlServerAgentJob(BaseModel):
    job_id: str
    name: str
    enabled: bool = True
    owner: str | None = None
    description: str | None = None
    last_status: str
    # SQL Agent run_date/run_time are server-local values with no persisted
    # timezone offset. The UI labels this accordingly.
    last_run_at: datetime | None = None
    last_duration_seconds: int | None = None
    last_message: str | None = None
    running: bool = False


class SqlServerAgentHealth(BaseModel):
    available: bool = True
    enabled_jobs: int | None = None
    failed_jobs: int | None = None
    running_jobs: int | None = None
    jobs: list[SqlServerAgentJob] = Field(default_factory=list)


class SqlServerHealthResponse(BaseModel):
    available: bool = True
    database_name: str | None = None
    generation: str | None = None
    database: SqlServerDatabaseHealth = Field(default_factory=SqlServerDatabaseHealth)
    transaction_log: SqlServerLogHealth = Field(default_factory=SqlServerLogHealth)
    workload: SqlServerWorkloadHealth = Field(default_factory=SqlServerWorkloadHealth)
    tempdb: SqlServerTempDbHealth = Field(default_factory=SqlServerTempDbHealth)
    agent: SqlServerAgentHealth = Field(default_factory=SqlServerAgentHealth)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime
