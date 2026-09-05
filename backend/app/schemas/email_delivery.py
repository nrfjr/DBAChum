from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class EmailProvider(str, Enum):
    BREVO = "brevo"
    SMTP = "smtp"


class SmtpSecurity(str, Enum):
    STARTTLS = "starttls"
    SSL = "ssl"
    NONE = "none"


class EmailDeliveryStatus(str, Enum):
    QUEUED = "queued"
    RETRY = "retry"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"


class EmailSettingsResponse(BaseModel):
    enabled: bool = False
    provider: EmailProvider = EmailProvider.BREVO
    sender_name: str = "DBAChum Alerts"
    sender_email: EmailStr | None = None
    reply_to_email: EmailStr | None = None
    application_url: str | None = None
    max_retries: int = 3

    has_brevo_api_key: bool = False

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_security: SmtpSecurity = SmtpSecurity.STARTTLS
    smtp_username: str | None = None
    has_smtp_password: bool = False

    updated_at: datetime | None = None
    updated_by: str | None = None


class EmailSettingsUpdate(BaseModel):
    enabled: bool = False
    provider: EmailProvider = EmailProvider.BREVO
    sender_name: str = Field(default="DBAChum Alerts", min_length=1, max_length=120)
    sender_email: EmailStr | None = None
    reply_to_email: EmailStr | None = None
    application_url: str | None = Field(default=None, max_length=500)
    max_retries: int = Field(default=3, ge=0, le=5)

    # Secrets are write-only. Blank/None means "keep the existing secret".
    brevo_api_key: str | None = Field(default=None, max_length=500)

    smtp_host: str | None = Field(default=None, max_length=255)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: SmtpSecurity = SmtpSecurity.STARTTLS
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password: str | None = Field(default=None, max_length=500)

    @field_validator(
        "sender_name",
        "application_url",
        "brevo_api_key",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        mode="before",
    )
    @classmethod
    def normalize_optional_strings(cls, value):
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_sender_when_enabled(self):
        if self.enabled and self.sender_email is None:
            raise ValueError("Sender email is required when email delivery is enabled.")
        return self


class EmailTestRequest(BaseModel):
    recipient_email: EmailStr
    recipient_name: str | None = Field(default=None, max_length=120)

    @field_validator("recipient_name")
    @classmethod
    def normalize_recipient_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class EmailTestResponse(BaseModel):
    sent: bool
    provider: EmailProvider
    recipient_email: EmailStr
    message_id: str | None = None


class EmailDeliveryResponse(BaseModel):
    id: str
    kind: str = "alert"
    status: EmailDeliveryStatus
    provider: EmailProvider
    recipient_email: EmailStr
    recipient_name: str | None = None
    subject: str
    alert_key: str | None = None
    source_name: str | None = None
    severity: str | None = None
    attempts: int = 0
    max_attempts: int = 1
    next_attempt_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None = None
    last_error: str | None = None
    provider_message_id: str | None = None


class EmailDeliverySummary(BaseModel):
    queued: int = 0
    retry: int = 0
    sent: int = 0
    failed: int = 0
