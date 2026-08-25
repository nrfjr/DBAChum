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
