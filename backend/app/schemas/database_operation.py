from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SessionOperation(str, Enum):
    TERMINATE = "terminate"
    DISCONNECT = "disconnect"
    CANCEL_QUERY = "cancel_query"


class StorageOperation(str, Enum):
    RESIZE_FILE = "resize_file"
    ADD_FILE = "add_file"


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

    # Existing file target. Oracle accepts datafile id through file_id and SQL
    # Server uses logical_name. file_name is retained as a portable fallback.
    file_id: int | None = Field(default=None, ge=1)
    file_name: str | None = Field(default=None, max_length=2048)
    logical_name: str | None = Field(default=None, max_length=128)

    # ADD FILE inputs.
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
        elif self.action == StorageOperation.ADD_FILE:
            if self.max_size_mb is not None and self.max_size_mb < self.size_mb:
                raise ValueError("max_size_mb cannot be smaller than size_mb.")
        return self


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
