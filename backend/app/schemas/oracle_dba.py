from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class OracleSessionItem(BaseModel):
    sid: int
    serial_number: int

    username: str | None = None
    status: str

    os_user: str | None = None
    machine: str | None = None
    program: str | None = None
    module: str | None = None

    sql_id: str | None = None
    sql_exec_start: datetime | None = None

    event: str | None = None
    wait_class: str | None = None

    blocking_instance: int | None = None
    blocking_session: int | None = None

    state_seconds: int

    logon_time: datetime | None = None


class OracleSessionsResponse(BaseModel):
    available: bool = True

    total: int = 0
    active: int = 0
    blocked: int = 0
    long_running: int = 0

    long_running_threshold_seconds: int = 60

    items: list[OracleSessionItem] = Field(
        default_factory=list
    )

    warning: str | None = None
    checked_at: datetime


class OracleTablespaceItem(BaseModel):
    name: str
    contents: str
    status: str

    used_bytes: int
    capacity_bytes: int

    used_percent: float


class OracleFraSummary(BaseModel):
    destination: str | None = None

    limit_bytes: int
    used_bytes: int
    reclaimable_bytes: int

    number_of_files: int

    used_percent: float | None = None


class OracleStorageResponse(BaseModel):
    tablespaces_available: bool = True
    fra_available: bool = True

    tablespaces: list[OracleTablespaceItem] = Field(
        default_factory=list
    )

    fra: OracleFraSummary | None = None

    warnings: list[str] = Field(
        default_factory=list
    )

    checked_at: datetime


class OracleActiveSqlItem(BaseModel):
    sid: int
    serial_number: int

    username: str | None = None

    sql_id: str
    sql_exec_start: datetime | None = None

    active_seconds: int

    module: str | None = None
    machine: str | None = None

    event: str | None = None
    wait_class: str | None = None

    sql_text: str | None = None


class OracleActivityResponse(BaseModel):
    available: bool = True

    items: list[OracleActiveSqlItem] = Field(
        default_factory=list
    )

    warning: str | None = None
    checked_at: datetime

class OracleDatabaseUserItem(BaseModel):
    username: str
    status: str

    default_tablespace: str | None = None
    temporary_tablespace: str | None = None
    profile: str | None = None

    created_at: datetime | None = None
    lock_date: datetime | None = None
    expiry_date: datetime | None = None


class OracleDatabaseUsersResponse(BaseModel):
    available: bool = True

    total: int = 0
    open: int = 0
    locked: int = 0
    expired: int = 0

    items: list[OracleDatabaseUserItem] = Field(
        default_factory=list
    )

    warning: str | None = None
    checked_at: datetime

class OracleReferenceRole(BaseModel):
    name: str
    admin_option: bool = False
    default_role: bool = False
    sensitive: bool = False


class OracleReferenceSystemPrivilege(BaseModel):
    name: str
    admin_option: bool = False


class OracleReferenceUserResponse(BaseModel):
    username: str
    status: str

    default_tablespace: str | None = None
    temporary_tablespace: str | None = None
    profile: str | None = None

    roles: list[OracleReferenceRole] = Field(
        default_factory=list
    )
    system_privileges: list[OracleReferenceSystemPrivilege] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(
        default_factory=list
    )


class OracleCreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=8, max_length=128)

    reference_username: str | None = Field(
        default=None,
        max_length=30,
    )
    roles: list[str] = Field(
        default_factory=list,
        max_length=100,
    )

    default_tablespace: str | None = Field(
        default=None,
        max_length=30,
    )
    temporary_tablespace: str | None = Field(
        default=None,
        max_length=30,
    )
    profile: str | None = Field(
        default=None,
        max_length=30,
    )

    request_reference: str | None = Field(
        default=None,
        max_length=100,
    )
    requestor_name: str | None = Field(
        default=None,
        max_length=200,
    )
    remarks: str | None = Field(
        default=None,
        max_length=1000,
    )

    first_name: str | None = Field(
        default=None,
        max_length=100,
    )
    middle_name: str | None = Field(
        default=None,
        max_length=100,
    )
    last_name: str | None = Field(
        default=None,
        max_length=100,
    )
    employee_id: str | None = Field(
        default=None,
        max_length=100,
    )
    generate_ldif: bool = False
    ldap_profile_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_ldif_profile(self):
        if self.generate_ldif and not self.ldap_profile_id:
            raise ValueError("Select an LDAP profile when LDIF generation is enabled.")
        if not self.generate_ldif:
            self.ldap_profile_id = None
        return self


class OracleCreateUserResponse(BaseModel):
    username: str
    roles_applied: list[str] = Field(
        default_factory=list
    )
    audit_id: str
    status: str
    requester_ip: str | None = None
    ldif_filename: str | None = None
    ldif_content: str | None = None



class OracleManageableRole(BaseModel):
    name: str
    sensitive: bool = False


class OracleUserLifecycleStateResponse(BaseModel):
    username: str
    status: str
    locked: bool = False
    expired: bool = False
    default_tablespace: str | None = None
    temporary_tablespace: str | None = None
    profile: str | None = None
    created_at: datetime | None = None
    lock_date: datetime | None = None
    expiry_date: datetime | None = None
    roles: list[OracleReferenceRole] = Field(default_factory=list)
    system_privileges: list[OracleReferenceSystemPrivilege] = Field(default_factory=list)
    available_roles: list[OracleManageableRole] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OracleUserEditRequest(BaseModel):
    roles: list[str] = Field(default_factory=list, max_length=200)
    default_tablespace: str | None = Field(default=None, max_length=30)
    temporary_tablespace: str | None = Field(default=None, max_length=30)
    profile: str | None = Field(default=None, max_length=30)
    locked: bool | None = None


class OracleUserEditExecuteRequest(OracleUserEditRequest):
    request_reference: str | None = Field(default=None, max_length=100)


class OracleUserEditPreviewItem(BaseModel):
    component: str
    action: str
    label: str
    before: str | None = None
    after: str | None = None
    sensitive: bool = False


class OracleUserEditPreviewResponse(BaseModel):
    username: str
    generated_at: datetime
    ready_to_execute: bool = True
    changes: list[OracleUserEditPreviewItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OracleUserEditResponse(BaseModel):
    audit_id: str
    status: str
    username: str
    changes_applied: int = 0
    after: OracleUserLifecycleStateResponse
    error: str | None = None


class OracleUserPasswordResetRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)
    expire_after_reset: bool = False
    request_reference: str | None = Field(default=None, max_length=100)


class OracleUserAccountActionRequest(BaseModel):
    action: str
    request_reference: str | None = Field(default=None, max_length=100)


class OracleUserLifecycleActionResponse(BaseModel):
    audit_id: str
    status: str
    username: str
    action: str
    after: OracleUserLifecycleStateResponse
    error: str | None = None
