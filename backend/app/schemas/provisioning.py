import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


ProvisioningValueKind = Literal[
    "form",
    "generated",
    "sequence",
    "custom",
    "null",
    "omit",
]


ORACLE_SEQUENCE_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_$#]{0,29}$")


class ProvisioningColumnMapping(BaseModel):
    column_name: str = Field(min_length=1, max_length=128)
    value_kind: ProvisioningValueKind = "omit"
    value_key: str | None = Field(default=None, max_length=128)
    custom_value: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_mapping(self):
        self.column_name = self.column_name.strip().upper()

        if self.value_key is not None:
            self.value_key = self.value_key.strip() or None

        if self.value_kind in {"form", "generated", "sequence"} and not self.value_key:
            raise ValueError("Mapped form/generated/sequence values require a source key.")

        if self.value_kind == "sequence":
            self.value_key = (self.value_key or "").upper()
            if not ORACLE_SEQUENCE_NAME_PATTERN.fullmatch(self.value_key):
                raise ValueError(
                    "Oracle sequence names must be simple 1-30 character identifiers."
                )

        if self.value_kind == "custom" and self.custom_value is None:
            raise ValueError("Custom mappings require a value.")

        if self.value_kind != "custom":
            self.custom_value = None

        if self.value_kind in {"custom", "null", "omit"}:
            self.value_key = None

        return self


class ProvisioningTableStep(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    connection_id: str = Field(min_length=1, max_length=64)
    owner: str = Field(min_length=1, max_length=128)
    table_name: str = Field(min_length=1, max_length=128)
    mappings: list[ProvisioningColumnMapping] = Field(default_factory=list, max_length=256)
    match_columns: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def normalize_step(self):
        self.name = self.name.strip()
        self.connection_id = self.connection_id.strip()
        self.owner = self.owner.strip().upper()
        self.table_name = self.table_name.strip().upper()

        if not any(mapping.value_kind != "omit" for mapping in self.mappings):
            raise ValueError("A table step must map at least one column.")

        columns = [mapping.column_name for mapping in self.mappings]
        if len(columns) != len(set(columns)):
            raise ValueError("A table step cannot map the same column twice.")

        self.match_columns = [
            column.strip().upper()
            for column in self.match_columns
            if column and column.strip()
        ]
        if len(self.match_columns) != len(set(self.match_columns)):
            raise ValueError("Upsert match columns cannot contain duplicates.")

        mapping_by_column = {mapping.column_name: mapping for mapping in self.mappings}
        for column in self.match_columns:
            mapping = mapping_by_column.get(column)
            if mapping is None:
                raise ValueError(
                    f'Upsert match column "{column}" must be present in the table mappings.'
                )
            stable_match = (
                mapping.value_kind == "custom"
                or (mapping.value_kind == "generated" and mapping.value_key == "username")
                or (mapping.value_kind == "form" and mapping.value_key == "employee_id")
            )
            if not stable_match:
                raise ValueError(
                    f'Upsert match column "{column}" must use generated username, employee ID, or a fixed custom literal.'
                )

        if not self.match_columns:
            inferred = [
                mapping.column_name
                for mapping in self.mappings
                if mapping.value_kind == "generated" and mapping.value_key == "username"
            ]
            if len(inferred) == 1:
                self.match_columns = inferred

        return self


class ProvisioningProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    schema_connection_id: str = Field(min_length=1, max_length=64)
    ldap_enabled: bool = False
    ldap_profile_id: str | None = Field(default=None, max_length=64)
    enabled: bool = True
    table_steps: list[ProvisioningTableStep] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def normalize_profile(self):
        self.name = self.name.strip()
        self.schema_connection_id = self.schema_connection_id.strip()
        self.description = (
            self.description.strip() or None
            if self.description is not None
            else None
        )
        self.ldap_profile_id = (
            self.ldap_profile_id.strip() or None
            if self.ldap_profile_id is not None
            else None
        )
        if self.ldap_enabled and not self.ldap_profile_id:
            raise ValueError("Select an LDAP profile when LDAP provisioning is enabled.")
        if not self.ldap_enabled:
            self.ldap_profile_id = None
        return self


class ProvisioningProfileCreate(ProvisioningProfileBase):
    pass


class ProvisioningProfileUpdate(ProvisioningProfileBase):
    pass


class ProvisioningProfileResponse(ProvisioningProfileBase):
    id: str
    ready: bool
    issues: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class LdapProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool = False
    host: str = Field(default="", max_length=255)
    port: int = Field(default=636, ge=1, le=65535)
    use_ssl: bool = True
    base_dn: str = Field(default="", max_length=500)
    bind_dn: str = Field(default="", max_length=500)
    ldif_template: str = Field(default="", max_length=20000)

    @model_validator(mode="after")
    def normalize_ldap(self):
        self.name = self.name.strip()
        self.description = (
            self.description.strip() or None
            if self.description is not None
            else None
        )
        self.host = self.host.strip()
        self.base_dn = self.base_dn.strip()
        self.bind_dn = self.bind_dn.strip()

        return self


def _validate_enabled_ldap(profile):
    if profile.enabled:
        if not profile.host:
            raise ValueError("LDAP host is required when LDAP is enabled.")
        if not profile.base_dn:
            raise ValueError("LDAP base DN is required when LDAP is enabled.")
        if not profile.bind_dn:
            raise ValueError("LDAP bind DN is required when LDAP is enabled.")
    return profile


class LdapProfileCreate(LdapProfileBase):
    bind_password: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_enabled_profile(self):
        return _validate_enabled_ldap(self)


class LdapProfileUpdate(LdapProfileBase):
    bind_password: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def validate_enabled_profile(self):
        return _validate_enabled_ldap(self)


class LdapProfileResponse(LdapProfileBase):
    id: str
    configured: bool
    has_bind_password: bool
    migrated_from_legacy: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LdapProfileTestResponse(BaseModel):
    success: bool
    connect_ok: bool
    bind_ok: bool
    base_dn_ok: bool
    message: str


# Backward-compatible schema aliases for the old singleton /provisioning/ldap API.
class LdapSettingsUpdate(BaseModel):
    enabled: bool = False
    host: str = Field(default="", max_length=255)
    port: int = Field(default=636, ge=1, le=65535)
    use_ssl: bool = True
    base_dn: str = Field(default="", max_length=500)
    bind_dn: str = Field(default="", max_length=500)
    bind_password: str | None = Field(default=None, max_length=512)
    ldif_template: str = Field(default="", max_length=20000)


class LdapSettingsResponse(BaseModel):
    configured: bool
    enabled: bool
    host: str
    port: int
    use_ssl: bool
    base_dn: str
    bind_dn: str
    has_bind_password: bool
    ldif_template: str
    updated_at: datetime | None = None


class OracleMetadataSchema(BaseModel):
    name: str


class OracleMetadataTable(BaseModel):
    owner: str
    name: str


class OracleMetadataSequence(BaseModel):
    owner: str
    name: str


class OracleMetadataColumn(BaseModel):
    name: str
    data_type: str
    data_length: int | None = None
    nullable: bool
    data_default: str | None = None
    column_id: int


class ProvisioningSourceOption(BaseModel):
    key: str
    label: str
    kind: Literal["form", "generated"]

class ProvisioningPreviewRequest(BaseModel):
    username: str | None = Field(default=None, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    first_name: str | None = Field(default=None, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    employee_id: str | None = Field(default=None, max_length=100)
    reference_user: str | None = Field(default=None, max_length=30)
    requestor: str | None = Field(default=None, max_length=200)
    request_reference: str | None = Field(default=None, max_length=100)
    remarks: str | None = Field(default=None, max_length=1000)


class ProvisioningPreviewRole(BaseModel):
    name: str
    sensitive: bool = False
    will_copy: bool = False


class ProvisioningPreviewColumn(BaseModel):
    column_name: str
    source: str
    display_value: str | None = None
    sensitive: bool = False
    expression: bool = False


class ProvisioningPreviewTableStep(BaseModel):
    index: int
    name: str
    connection_id: str
    connection_name: str
    owner: str
    table_name: str
    match_columns: list[str] = Field(default_factory=list)
    match_values: dict[str, str | None] = Field(default_factory=dict)
    existing_rows: int
    planned_action: Literal["insert", "update", "conflict"]
    columns: list[ProvisioningPreviewColumn] = Field(default_factory=list)


class ProvisioningPreviewLdap(BaseModel):
    enabled: bool = False
    profile_id: str | None = None
    profile_name: str | None = None
    filename: str | None = None
    template_valid: bool = False


class ProvisioningPreviewResponse(BaseModel):
    dry_run: bool = True
    ready_to_execute: bool = True
    profile_id: str
    profile_name: str
    schema_connection_id: str
    schema_connection_name: str
    username: str
    account_exists: bool = False
    account_action: Literal["create", "alter"] = "create"
    requester_ip: str | None = None
    operator_username: str
    generated_at: datetime
    reference_user: str | None = None
    default_tablespace: str | None = None
    temporary_tablespace: str | None = None
    oracle_profile: str | None = None
    roles: list[ProvisioningPreviewRole] = Field(default_factory=list)
    table_steps: list[ProvisioningPreviewTableStep] = Field(default_factory=list)
    ldap: ProvisioningPreviewLdap
    warnings: list[str] = Field(default_factory=list)
