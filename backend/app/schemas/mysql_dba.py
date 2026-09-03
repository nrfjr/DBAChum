from datetime import datetime

from pydantic import BaseModel, Field


class MySqlSessionItem(BaseModel):
    connection_id: int
    user: str | None = None
    host: str | None = None
    database: str | None = None
    command: str | None = None
    state: str | None = None
    elapsed_seconds: int
    blocking_connection_id: int | None = None
    sql_text: str | None = None


class MySqlSessionsResponse(BaseModel):
    available: bool = True
    database_name: str | None = None
    scope: str = "instance"
    processlist_source: str | None = None
    performance_schema_enabled: bool | None = None
    total: int | None = None
    active: int | None = None
    blocked: int | None = None
    long_running: int | None = None
    long_running_threshold_seconds: int = 60
    items: list[MySqlSessionItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime


class MySqlSchemaStorageItem(BaseModel):
    schema_name: str
    data_bytes: int
    index_bytes: int
    total_bytes: int
    table_count: int


class MySqlTableStorageItem(BaseModel):
    schema_name: str | None = None
    table_name: str
    engine: str | None = None
    data_bytes: int
    index_bytes: int
    total_bytes: int
    rows_estimate: int | None = None
    collation: str | None = None


class MySqlStorageResponse(BaseModel):
    available: bool = True
    database_name: str | None = None
    scope: str = "instance"
    data_bytes: int
    index_bytes: int
    total_bytes: int
    table_count: int = 0
    schema_count: int = 0
    schemas: list[MySqlSchemaStorageItem] = Field(default_factory=list)
    tables: list[MySqlTableStorageItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime


class MySqlActivityItem(BaseModel):
    connection_id: int
    user: str | None = None
    host: str | None = None
    database: str | None = None
    command: str | None = None
    elapsed_seconds: int
    state: str | None = None
    transaction_id: str | None = None
    transaction_state: str | None = None
    transaction_started: datetime | None = None
    transaction_wait_started: datetime | None = None
    wait_event: str | None = None
    wait_object: str | None = None
    blocking_connection_id: int | None = None
    sql_text: str | None = None


class MySqlActivityResponse(BaseModel):
    available: bool = True
    database_name: str | None = None
    scope: str = "instance"
    processlist_source: str | None = None
    performance_schema_enabled: bool | None = None
    items: list[MySqlActivityItem] = Field(default_factory=list)
    warning: str | None = None
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime


class MySqlConnectionHealth(BaseModel):
    current: int | None = None
    maximum: int | None = None
    utilization_percent: float | None = None
    max_used: int | None = None
    max_used_percent: float | None = None
    total_since_startup: int | None = None
    aborted_connects: int | None = None
    aborted_clients: int | None = None


class MySqlWorkloadHealth(BaseModel):
    threads_running: int | None = None
    slow_queries: int | None = None
    questions: int | None = None
    longest_active_seconds: int | None = None
    threads_created: int | None = None


class MySqlInnoDbHealth(BaseModel):
    active_transactions: int | None = None
    blocked_transactions: int | None = None
    oldest_transaction_seconds: int | None = None
    buffer_pool_size_bytes: int | None = None
    buffer_pool_data_bytes: int | None = None
    buffer_pool_used_percent: float | None = None


class MySqlTemporaryTableHealth(BaseModel):
    created: int | None = None
    created_on_disk: int | None = None
    disk_percent: float | None = None


class MySqlServerHealth(BaseModel):
    uptime_seconds: int | None = None
    read_only: bool | None = None
    slow_query_log: bool | None = None
    long_query_time_seconds: float | None = None


class MySqlHealthResponse(BaseModel):
    available: bool = True
    database_name: str | None = None
    scope: str = "instance"
    product: str | None = None
    generation: str | None = None
    performance_schema_enabled: bool = False
    processlist_source: str | None = None
    connections: MySqlConnectionHealth
    workload: MySqlWorkloadHealth
    innodb: MySqlInnoDbHealth
    temporary_tables: MySqlTemporaryTableHealth
    server: MySqlServerHealth
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime


class MySqlPrivilegeItem(BaseModel):
    privilege: str
    scope: str
    grant_option: bool = False


class MySqlElevatedFinding(BaseModel):
    principal: str
    severity: str
    source: str
    detail: str


class MySqlAccountItem(BaseModel):
    user: str
    host: str
    account: str
    auth_plugin: str | None = None
    account_locked: bool | None = None
    password_expired: bool | None = None
    is_role: bool = False
    default_role: str | None = None
    ssl_type: str | None = None
    password_last_changed: datetime | None = None
    current_identity: bool = False
    login_identity: str | None = None
    wildcard_host: bool = False
    remote_host: bool = False
    grants_visible: bool = False
    grants: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    privileges: list[MySqlPrivilegeItem] = Field(default_factory=list)
    elevated_findings: list[MySqlElevatedFinding] = Field(default_factory=list)


class MySqlSecurityResponse(BaseModel):
    available: bool = True
    database_name: str | None = None
    scope: str = "instance"
    product: str | None = None
    generation: str | None = None
    metadata_source: str | None = None
    grants_source: str = "SHOW GRANTS"
    complete_account_list: bool = False
    account_count: int = 0
    anonymous_account_count: int = 0
    wildcard_host_count: int = 0
    role_account_count: int = 0
    accounts: list[MySqlAccountItem] = Field(default_factory=list)
    elevated_findings: list[MySqlElevatedFinding] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime
