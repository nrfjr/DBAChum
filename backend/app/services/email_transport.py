from __future__ import annotations

import asyncio
import html
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import httpx

from app.core.exceptions import AppError
from app.schemas.email_delivery import EmailProvider, SmtpSecurity
from app.services.email_settings import email_provider_secret, ready_email_settings


BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


@dataclass(frozen=True)
class OutboundEmail:
    recipient_email: str
    recipient_name: str | None
    subject: str
    text_content: str
    html_content: str


@dataclass(frozen=True)
class EmailSendResult:
    provider: str
    message_id: str | None = None


def _safe_provider_error(message: str, *, code: str = "EMAIL_SEND_FAILED") -> AppError:
    normalized = " ".join(str(message or "").split())
    if len(normalized) > 500:
        normalized = normalized[:497] + "..."
    return AppError(
        normalized or "Email delivery failed.",
        code=code,
        status_code=502,
    )


async def _send_brevo(settings_document: dict[str, Any], message: OutboundEmail) -> EmailSendResult:
    api_key = email_provider_secret(settings_document)
    if not api_key:
        raise AppError(
            "Brevo API key is not configured.",
            code="BREVO_API_KEY_REQUIRED",
            status_code=400,
        )

    payload: dict[str, Any] = {
        "sender": {
            "name": settings_document.get("sender_name") or "DBAChum Alerts",
            "email": settings_document["sender_email"],
        },
        "to": [
            {
                "email": message.recipient_email,
                **(
                    {"name": message.recipient_name}
                    if message.recipient_name
                    else {}
                ),
            }
        ],
        "subject": message.subject,
        "htmlContent": message.html_content,
        "tags": ["dbachum", "alert"],
    }
    if settings_document.get("reply_to_email"):
        payload["replyTo"] = {"email": settings_document["reply_to_email"]}

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                BREVO_SEND_URL,
                headers={
                    "accept": "application/json",
                    "api-key": api_key,
                    "content-type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise _safe_provider_error(
            f"Brevo request failed: {exc.__class__.__name__}"
        ) from exc

    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            detail = str(body.get("message") or body.get("code") or "")
        except Exception:
            detail = response.text[:250]
        raise _safe_provider_error(
            f"Brevo rejected the email ({response.status_code})"
            + (f": {detail}" if detail else "."),
            code="BREVO_SEND_FAILED",
        )

    message_id = None
    try:
        message_id = response.json().get("messageId")
    except Exception:
        pass

    return EmailSendResult(
        provider=EmailProvider.BREVO.value,
        message_id=str(message_id) if message_id else None,
    )


def _smtp_message(settings_document: dict[str, Any], message: OutboundEmail) -> EmailMessage:
    email = EmailMessage()
    email["Subject"] = message.subject
    email["From"] = formataddr(
        (
            str(settings_document.get("sender_name") or "DBAChum Alerts"),
            str(settings_document["sender_email"]),
        )
    )
    email["To"] = formataddr(
        (
            message.recipient_name or "",
            message.recipient_email,
        )
    )
    if settings_document.get("reply_to_email"):
        email["Reply-To"] = str(settings_document["reply_to_email"])

    email.set_content(message.text_content)
    email.add_alternative(message.html_content, subtype="html")
    return email


def _send_smtp_sync(settings_document: dict[str, Any], message: OutboundEmail) -> EmailSendResult:
    host = str(settings_document.get("smtp_host") or "").strip()
    port = int(settings_document.get("smtp_port") or 587)
    security = str(settings_document.get("smtp_security") or SmtpSecurity.STARTTLS.value)
    username = str(settings_document.get("smtp_username") or "").strip() or None
    password = email_provider_secret(settings_document)

    email = _smtp_message(settings_document, message)
    context = ssl.create_default_context()

    try:
        if security == SmtpSecurity.SSL.value:
            client = smtplib.SMTP_SSL(host, port, timeout=20, context=context)
        else:
            client = smtplib.SMTP(host, port, timeout=20)

        with client:
            client.ehlo()
            if security == SmtpSecurity.STARTTLS.value:
                client.starttls(context=context)
                client.ehlo()
            if username:
                if not password:
                    raise AppError(
                        "SMTP password is not configured.",
                        code="SMTP_PASSWORD_REQUIRED",
                        status_code=400,
                    )
                client.login(username, password)
            response = client.send_message(email)
    except AppError:
        raise
    except (smtplib.SMTPException, OSError) as exc:
        raise _safe_provider_error(
            f"SMTP delivery failed: {exc.__class__.__name__}",
            code="SMTP_SEND_FAILED",
        ) from exc

    # smtplib returns a mapping only for recipients the SMTP server refused.
    if response:
        raise _safe_provider_error(
            "SMTP server refused the recipient.",
            code="SMTP_RECIPIENT_REFUSED",
        )

    return EmailSendResult(provider=EmailProvider.SMTP.value)


async def send_email(
    settings_document: dict[str, Any],
    message: OutboundEmail,
    *,
    require_enabled: bool = True,
) -> EmailSendResult:
    ready_email_settings(settings_document, require_enabled=require_enabled)
    provider = str(settings_document.get("provider") or EmailProvider.BREVO.value)

    if provider == EmailProvider.BREVO.value:
        return await _send_brevo(settings_document, message)
    if provider == EmailProvider.SMTP.value:
        return await asyncio.to_thread(
            _send_smtp_sync,
            settings_document,
            message,
        )

    raise AppError(
        "Unsupported email provider.",
        code="EMAIL_PROVIDER_UNSUPPORTED",
        status_code=400,
    )


def build_test_message(recipient_email: str, recipient_name: str | None = None) -> OutboundEmail:
    display = html.escape(recipient_name or recipient_email)
    return OutboundEmail(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        subject="DBAChum email delivery test",
        text_content=(
            "DBAChum email delivery is working.\n\n"
            f"Recipient: {recipient_email}\n"
            "This message was sent from Settings > Alerts & Email."
        ),
        html_content=(
            "<html><body style=\"font-family:Arial,sans-serif;line-height:1.5\">"
            "<h2>DBAChum email delivery is working</h2>"
            f"<p>Hello {display},</p>"
            "<p>This message confirms that the configured DBAChum email provider can send transactional mail.</p>"
            "<p style=\"color:#666\">Sent from Settings &gt; Alerts &amp; Email.</p>"
            "</body></html>"
        ),
    )
