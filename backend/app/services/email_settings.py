from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.exceptions import AppError
from app.core.security import decrypt_secret, encrypt_secret
from app.schemas.email_delivery import (
    EmailProvider,
    EmailSettingsResponse,
    EmailSettingsUpdate,
    SmtpSecurity,
)


EMAIL_SETTINGS_ID = "email"
EMAIL_SETTINGS_COLLECTION = "notification_settings"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _defaults() -> dict[str, Any]:
    return {
        "_id": EMAIL_SETTINGS_ID,
        "enabled": False,
        "provider": EmailProvider.BREVO.value,
        "sender_name": "DBAChum Alerts",
        "sender_email": None,
        "reply_to_email": None,
        "application_url": None,
        "max_retries": 3,
        "smtp_host": None,
        "smtp_port": 587,
        "smtp_security": SmtpSecurity.STARTTLS.value,
        "smtp_username": None,
    }


def email_settings_to_response(document: dict | None) -> EmailSettingsResponse:
    data = {**_defaults(), **(document or {})}
    return EmailSettingsResponse(
        enabled=bool(data.get("enabled", False)),
        provider=data.get("provider", EmailProvider.BREVO.value),
        sender_name=str(data.get("sender_name") or "DBAChum Alerts"),
        sender_email=data.get("sender_email"),
        reply_to_email=data.get("reply_to_email"),
        application_url=data.get("application_url"),
        max_retries=int(data.get("max_retries") or 0),
        has_brevo_api_key=bool(data.get("brevo_api_key_encrypted")),
        smtp_host=data.get("smtp_host"),
        smtp_port=int(data.get("smtp_port") or 587),
        smtp_security=data.get("smtp_security", SmtpSecurity.STARTTLS.value),
        smtp_username=data.get("smtp_username"),
        has_smtp_password=bool(data.get("smtp_password_encrypted")),
        updated_at=data.get("updated_at"),
        updated_by=data.get("updated_by"),
    )


async def get_email_settings_document(database) -> dict:
    document = await database[EMAIL_SETTINGS_COLLECTION].find_one(
        {"_id": EMAIL_SETTINGS_ID}
    )
    return {**_defaults(), **(document or {})}


async def get_email_settings(database) -> EmailSettingsResponse:
    return email_settings_to_response(
        await get_email_settings_document(database)
    )


def _validate_ready(document: dict, *, require_enabled: bool) -> None:
    if require_enabled and not document.get("enabled"):
        raise AppError(
            "Email delivery is disabled.",
            code="EMAIL_DELIVERY_DISABLED",
            status_code=409,
        )

    sender_email = str(document.get("sender_email") or "").strip()
    if not sender_email:
        raise AppError(
            "A sender email address is required before sending email.",
            code="EMAIL_SENDER_REQUIRED",
            status_code=400,
        )

    provider = str(document.get("provider") or EmailProvider.BREVO.value)
    if provider == EmailProvider.BREVO.value:
        if not document.get("brevo_api_key_encrypted"):
            raise AppError(
                "A Brevo API key is required for the Brevo provider.",
                code="BREVO_API_KEY_REQUIRED",
                status_code=400,
            )
        return

    if provider == EmailProvider.SMTP.value:
        if not str(document.get("smtp_host") or "").strip():
            raise AppError(
                "SMTP host is required for the SMTP provider.",
                code="SMTP_HOST_REQUIRED",
                status_code=400,
            )
        if document.get("smtp_username") and not document.get("smtp_password_encrypted"):
            raise AppError(
                "SMTP password is required when an SMTP username is configured.",
                code="SMTP_PASSWORD_REQUIRED",
                status_code=400,
            )
        return

    raise AppError(
        "Unsupported email provider.",
        code="EMAIL_PROVIDER_UNSUPPORTED",
        status_code=400,
    )


async def update_email_settings(
    database,
    data: EmailSettingsUpdate,
    *,
    updated_by: str,
) -> EmailSettingsResponse:
    existing = await get_email_settings_document(database)
    now = _utcnow()

    document: dict[str, Any] = {
        "enabled": data.enabled,
        "provider": data.provider.value,
        "sender_name": data.sender_name,
        "sender_email": str(data.sender_email) if data.sender_email else None,
        "reply_to_email": str(data.reply_to_email) if data.reply_to_email else None,
        "application_url": (
            data.application_url.rstrip("/")
            if data.application_url
            else None
        ),
        "max_retries": data.max_retries,
        "smtp_host": data.smtp_host,
        "smtp_port": data.smtp_port,
        "smtp_security": data.smtp_security.value,
        "smtp_username": data.smtp_username,
        "updated_at": now,
        "updated_by": updated_by,
    }

    if data.brevo_api_key:
        document["brevo_api_key_encrypted"] = encrypt_secret(data.brevo_api_key)
    elif existing.get("brevo_api_key_encrypted"):
        document["brevo_api_key_encrypted"] = existing["brevo_api_key_encrypted"]

    if data.smtp_password:
        document["smtp_password_encrypted"] = encrypt_secret(data.smtp_password)
    elif existing.get("smtp_password_encrypted"):
        document["smtp_password_encrypted"] = existing["smtp_password_encrypted"]

    candidate = {**_defaults(), **existing, **document}
    if data.enabled:
        _validate_ready(candidate, require_enabled=True)

    await database[EMAIL_SETTINGS_COLLECTION].update_one(
        {"_id": EMAIL_SETTINGS_ID},
        {
            "$set": document,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    stored = await get_email_settings_document(database)
    return email_settings_to_response(stored)


def ready_email_settings(document: dict, *, require_enabled: bool = True) -> dict:
    _validate_ready(document, require_enabled=require_enabled)
    return document


def email_provider_secret(document: dict) -> str | None:
    provider = str(document.get("provider") or "")
    if provider == EmailProvider.BREVO.value:
        encrypted = document.get("brevo_api_key_encrypted")
    elif provider == EmailProvider.SMTP.value:
        encrypted = document.get("smtp_password_encrypted")
    else:
        encrypted = None

    if not encrypted:
        return None
    return decrypt_secret(str(encrypted))
