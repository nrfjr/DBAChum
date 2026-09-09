from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SessionOperation(str, Enum):
    TERMINATE = "terminate"
    DISCONNECT = "disconnect"
    CANCEL_QUERY = "cancel_query"


class StorageOperation(str, Enum):
    RESIZE_FILE = "resize_file"
    ADD_FILE = "add_file"
    CREATE_TABLESPACE = "create_tablespace"




class ParameterOperation(str, Enum):
    SET = "set"


class MaintenanceOperation(str, Enum):
    DELETE_ARCHIVELOGS = "delete_archivelogs"
    DELETE_OBSOLETE = "delete_obsolete"


    GATHER_SCHEMA_STATS = "gather_schema_stats"
    GATHER_TABLE_STATS = "gather_table_stats"
    RECOMPILE_INVALID = "recompile_invalid"
    REBUILD_UNUSABLE_INDEXES = "rebuild_unusable_indexes"
    PURGE_RECYCLEBIN = "purge_recyclebin"
    CHECK_INTEGRITY = "check_integrity"
    UPDATE_STATISTICS = "update_statistics"
    SHRINK_DATABASE = "shrink_database"
    ANALYZE_TABLE = "analyze_table"
    OPTIMIZE_TABLE = "optimize_table"
    CHECK_TABLE = "check_table"


class BackupOperation(str, Enum):
    FULL = "full"
    DIFFERENTIAL = "differential"
    LOG = "log"
    ARCHIVELOG = "archivelog"
    DATABASE_PLUS_ARCHIVELOG = "database_plus_archivelog"

class AccountOperation(str, Enum):
    ENABLE = "enable"
    DISABLE = "disable"
    RESET_PASSWORD = "reset_password"


class AccessOperation(str, Enum):
    GRANT_ROLE = "grant_role"
    REVOKE_ROLE = "revoke_role"
    GRANT_PRIVILEGE = "grant_privilege"
    REVOKE_PRIVILEGE = "revoke_privilege"


class SessionOperationRequest(BaseModel):
    action: SessionOperation
    session_id: int = Field(ge=1)
    serial_number: int | None = Field(default=None, ge=1)
    request_reference: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_oracle_identifier_shape(self):
        if self.serial_number is not None and self.serial_number <= 0:
            raise ValueError("serial_number must be greater than zero.")
        return self


class StorageOperationRequest(BaseModel):
    action: StorageOperation
    size_mb: int = Field(ge=1, le=16_777_216)

    file_id: int | None = Field(default=None, ge=1)
    file_name: str | None = Field(default=None, max_length=2048)
    logical_name: str | None = Field(default=None, max_length=128)

    tablespace_name: str | None = Field(default=None, max_length=128)
    physical_name: str | None = Field(default=None, max_length=2048)
    file_type: str = Field(default="data", pattern="^(data|log)$")
    autoextend: bool = True
    growth_mb: int | None = Field(default=None, ge=1, le=1_048_576)
    max_size_mb: int | None = Field(default=None, ge=1, le=16_777_216)
    request_reference: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_operation_fields(self):
        if self.action == StorageOperation.RESIZE_FILE:
            if self.file_id is None and not self.file_name and not self.logical_name:
                raise ValueError(
                    "Resize requires file_id, file_name, or logical_name."
                )
        elif self.action in {StorageOperation.ADD_FILE, StorageOperation.CREATE_TABLESPACE}:
            if self.action == StorageOperation.CREATE_TABLESPACE and not self.tablespace_name:
                raise ValueError("create_tablespace requires tablespace_name.")
            if self.max_size_mb is not None and self.max_size_mb < self.size_mb:
                raise ValueError("max_size_mb cannot be smaller than size_mb.")
        return self


class ParameterOperationRequest(BaseModel):
    action: ParameterOperation = ParameterOperation.SET
    name: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=4000)
    apply_mode: str = Field(default="both", pattern="^(runtime|persistent|both)$")
    request_reference: str | None = Field(default=None, max_length=100)


class MaintenanceOperationRequest(BaseModel):
    action: MaintenanceOperation
    server_id: str | None = Field(default=None, max_length=64)
    oracle_sid: str | None = Field(default=None, max_length=128)
    older_than_days: int | None = Field(default=None, ge=1, le=3650)
    backed_up_times: int = Field(default=1, ge=0, le=99)
    schema_name: str | None = Field(default=None, max_length=128)
    table_name: str | None = Field(default=None, max_length=256)
    target_percent: int | None = Field(default=None, ge=0, le=99)
    request_reference: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_maintenance(self):
        if self.action == MaintenanceOperation.DELETE_ARCHIVELOGS and self.older_than_days is None:
            raise ValueError("older_than_days is required for archive log cleanup.")
        if self.action in {MaintenanceOperation.GATHER_TABLE_STATS, MaintenanceOperation.ANALYZE_TABLE, MaintenanceOperation.OPTIMIZE_TABLE, MaintenanceOperation.CHECK_TABLE} and not self.table_name:
            raise ValueError("table_name is required for this maintenance operation.")
        return self


class BackupOperationRequest(BaseModel):
    action: BackupOperation
    server_id: str | None = Field(default=None, max_length=64)
    destination: str | None = Field(default=None, max_length=2048)
    oracle_sid: str | None = Field(default=None, max_length=128)
    copy_only: bool = False
    cleanup_archivelogs_after: bool = False
    archivelog_retention_days: int = Field(default=2, ge=1, le=3650)
    request_reference: str | None = Field(default=None, max_length=100)


class AccountOperationRequest(BaseModel):
    action: AccountOperation
    account_name: str = Field(min_length=1, max_length=256)
    host: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=1, max_length=256)
    request_reference: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_password_action(self):
        if self.action == AccountOperation.RESET_PASSWORD and not self.password:
            raise ValueError("Password is required for reset_password.")
        return self


class AccessOperationRequest(BaseModel):
    action: AccessOperation
    principal: str = Field(min_length=1, max_length=256)
    host: str | None = Field(default=None, max_length=255)
    role_name: str | None = Field(default=None, max_length=256)
    privilege: str | None = Field(default=None, max_length=128)
    object_name: str | None = Field(default=None, max_length=512)
    scope: str = Field(default="database", pattern="^(database|server)$")
    request_reference: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_access_target(self):
        if self.action in {AccessOperation.GRANT_ROLE, AccessOperation.REVOKE_ROLE}:
            if not self.role_name:
                raise ValueError("role_name is required for role operations.")
        else:
            if not self.privilege:
                raise ValueError("privilege is required for privilege operations.")
            if not self.object_name:
                raise ValueError("object_name is required for privilege operations.")
        return self
