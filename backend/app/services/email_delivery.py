from __future__ import annotations

import html
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import AppError
from app.schemas.email_delivery import (
    EmailDeliveryResponse,
    EmailDeliveryStatus,
    EmailProvider,
)
from app.services.email_settings import get_email_settings_document
from app.services.email_transport import OutboundEmail, build_test_message, send_email
from app.services.notification_subscriptions import (
    category_for_alert,
    email_subscription_matches_alert,
)
from app.services.users import (
    normalize_email,
    notification_preferences_from_document,
)


logger = logging.getLogger(__name__)

EMAIL_DELIVERIES_COLLECTION = "email_deliveries"
DELIVERY_RETENTION_DAYS = 30
MAX_BATCH_SIZE = 25


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _expires_at(now: datetime) -> datetime:
    return now + timedelta(days=DELIVERY_RETENTION_DAYS)


def _severity_rank(value: str | None) -> int:
    normalized = str(value or "").lower()
    return {"warning": 1, "critical": 2}.get(normalized, 0)


def should_enqueue_alert_email(existing: dict | None, updated: dict) -> bool:
    """Notify once when an incident becomes active and once on escalation.

    Alert rows are updated every collector sample. This guard is what prevents
    a persistent incident from generating an email every 30 seconds.
    """

    if str(updated.get("status") or "") != "active":
        return False

    previous_status = str((existing or {}).get("status") or "")
    if previous_status != "active":
        return True

    return _severity_rank(updated.get("severity")) > _severity_rank(
        (existing or {}).get("severity")
    )


def _incident_token(alert: dict) -> str:
    first_seen = alert.get("first_seen_at")
    if isinstance(first_seen, datetime):
        if first_seen.tzinfo is None:
            first_seen = first_seen.replace(tzinfo=timezone.utc)
        return first_seen.isoformat()
    return str(first_seen or "unknown")


def _alert_subject(alert: dict) -> str:
    severity = str(alert.get("severity") or "warning").upper()
    title = str(alert.get("title") or "DBAChum alert").strip()
    return f"[DBAChum] {severity} — {title}"


def _alert_message(
    alert: dict,
    *,
    recipient_email: str,
    recipient_name: str | None,
    application_url: str | None,
) -> OutboundEmail:
    severity = str(alert.get("severity") or "warning").upper()
    source_name = str(alert.get("source_name") or "Unknown source")
    source_type = str(alert.get("source_type") or "source").title()
    title = str(alert.get("title") or "DBAChum alert")
    detail = str(alert.get("message") or "")
    detected = alert.get("first_seen_at") or alert.get("last_seen_at")
    if isinstance(detected, datetime):
        if detected.tzinfo is None:
            detected = detected.replace(tzinfo=timezone.utc)
        detected_text = detected.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        detected_text = str(detected or "Unknown")

    rule_key = str(alert.get("rule_key") or "")
    engine = str(alert.get("source_engine") or "").strip()
    category = category_for_alert(
        rule_key,
        str(alert.get("source_type") or ""),
    ).value

    text_lines = [
        f"DBAChum — {severity}",
        "",
        title,
        detail,
        "",
        f"Source: {source_name}",
        f"Type: {source_type}",
    ]
    if engine:
        text_lines.append(f"Engine: {engine}")
    text_lines.append(f"Category: {category}")
    if rule_key:
        text_lines.append(f"Rule: {rule_key}")
    text_lines.append(f"Detected: {detected_text}")
    if application_url:
        text_lines.extend(["", f"Open DBAChum: {application_url}"])

    safe_severity = html.escape(severity)
    safe_title = html.escape(title)
    safe_detail = html.escape(detail)
    safe_source = html.escape(source_name)
    safe_type = html.escape(source_type)
    safe_detected = html.escape(detected_text)
    safe_engine = html.escape(engine)
    safe_category = html.escape(category.title())
    safe_rule = html.escape(rule_key)
    safe_url = html.escape(application_url or "", quote=True)

    rows = [
        f"<tr><td style='padding:4px 12px 4px 0;color:#666'>Source</td><td>{safe_source}</td></tr>",
        f"<tr><td style='padding:4px 12px 4px 0;color:#666'>Type</td><td>{safe_type}</td></tr>",
    ]
    if engine:
        rows.append(
            f"<tr><td style='padding:4px 12px 4px 0;color:#666'>Engine</td><td>{safe_engine}</td></tr>"
        )
    rows.append(
        f"<tr><td style='padding:4px 12px 4px 0;color:#666'>Category</td><td>{safe_category}</td></tr>"
    )
    if rule_key:
        rows.append(
            f"<tr><td style='padding:4px 12px 4px 0;color:#666'>Rule</td><td>{safe_rule}</td></tr>"
        )
    rows.append(
        f"<tr><td style='padding:4px 12px 4px 0;color:#666'>Detected</td><td>{safe_detected}</td></tr>"
    )

    open_button = ""
    if application_url:
        open_button = (
            "<p style='margin-top:22px'>"
            f"<a href='{safe_url}' style='display:inline-block;padding:10px 14px;border-radius:8px;background:#6d55c4;color:white;text-decoration:none'>Open DBAChum</a>"
            "</p>"
        )

    html_content = (
        "<html><body style='font-family:Arial,sans-serif;line-height:1.5;color:#222'>"
        f"<div style='font-size:12px;font-weight:700;letter-spacing:.08em;color:#666'>DBACHUM · {safe_severity}</div>"
        f"<h2 style='margin:8px 0 6px'>{safe_title}</h2>"
        f"<p style='margin-top:0'>{safe_detail}</p>"
        "<table style='border-collapse:collapse;margin-top:16px'>"
        + "".join(rows)
        + "</table>"
        + open_button
        + "<p style='margin-top:24px;color:#777;font-size:12px'>Delivery follows this user's DBAChum alert subscription.</p>"
        "</body></html>"
    )

    return OutboundEmail(
        recipient_email=recipient_email,
        recipient_name=recipient_name,
        subject=_alert_subject(alert),
        text_content="\n".join(text_lines),
        html_content=html_content,
    )


def _delivery_response(document: dict) -> EmailDeliveryResponse:
    return EmailDeliveryResponse(
        id=str(document["_id"]),
        kind=str(document.get("kind") or "alert"),
        status=document.get("status", EmailDeliveryStatus.QUEUED.value),
        provider=document.get("provider", EmailProvider.BREVO.value),
        recipient_email=document["recipient_email"],
        recipient_name=document.get("recipient_name"),
        subject=document.get("subject") or "DBAChum alert",
        alert_key=document.get("alert_key"),
        source_name=document.get("source_name"),
        severity=document.get("severity"),
        attempts=int(document.get("attempts") or 0),
        max_attempts=int(document.get("max_attempts") or 1),
        next_attempt_at=document.get("next_attempt_at"),
        created_at=document["created_at"],
        updated_at=document["updated_at"],
        sent_at=document.get("sent_at"),
        last_error=document.get("last_error"),
        provider_message_id=document.get("provider_message_id"),
    )


async def enqueue_alert_email_deliveries(database, alert: dict) -> int:
    settings_document = await get_email_settings_document(database)
    if not settings_document.get("enabled"):
        return 0

    users = await database.users.find(
        {
            "is_active": {"$ne": False},
            "email": {"$type": "string"},
            "notifications.email_enabled": True,
        }
    ).to_list(None)

    now = _utcnow()
    queued = 0
    provider = str(settings_document.get("provider") or EmailProvider.BREVO.value)
    max_attempts = 1 + int(settings_document.get("max_retries") or 0)
    application_url = settings_document.get("application_url")

    for user in users:
        recipient_email = normalize_email(user.get("email"))
        if not recipient_email:
            continue

        subscription = notification_preferences_from_document(user)
        if not email_subscription_matches_alert(
            subscription,
            alert,
            source_engine=alert.get("source_engine"),
        ):
            continue

        recipient_name = str(user.get("display_name") or user.get("username") or "").strip() or None
        message = _alert_message(
            alert,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            application_url=application_url,
        )

        event_key = ":".join(
            [
                "alert",
                str(alert.get("alert_key") or "unknown"),
                _incident_token(alert),
                str(alert.get("severity") or "warning"),
                str(user["_id"]),
            ]
        )
        document = {
            "event_key": event_key,
            "kind": "alert",
            "status": EmailDeliveryStatus.QUEUED.value,
            "provider": provider,
            "user_id": str(user["_id"]),
            "recipient_email": recipient_email,
            "recipient_name": recipient_name,
            "subject": message.subject,
            "text_content": message.text_content,
            "html_content": message.html_content,
            "alert_key": alert.get("alert_key"),
            "source_type": alert.get("source_type"),
            "source_id": alert.get("source_id"),
            "source_name": alert.get("source_name"),
            "source_engine": alert.get("source_engine"),
            "severity": alert.get("severity"),
            "rule_key": alert.get("rule_key"),
            "attempts": 0,
            "max_attempts": max_attempts,
            "next_attempt_at": now,
            "created_at": now,
            "updated_at": now,
            "expires_at": _expires_at(now),
            "last_error": None,
            "provider_message_id": None,
        }

        try:
            await database[EMAIL_DELIVERIES_COLLECTION].insert_one(document)
            queued += 1
        except DuplicateKeyError:
            # Same incident/severity/user has already been queued or sent.
            continue

    return queued


async def _mark_delivery_failure(database, document: dict, exc: Exception) -> None:
    now = _utcnow()
    attempts = int(document.get("attempts") or 0) + 1
    max_attempts = int(document.get("max_attempts") or 1)
    terminal = attempts >= max_attempts
    delay_seconds = min(1800, 60 * (2 ** max(0, attempts - 1)))
    error = getattr(exc, "message", None) or str(exc).strip() or exc.__class__.__name__
    if len(error) > 500:
        error = error[:497] + "..."

    await database[EMAIL_DELIVERIES_COLLECTION].update_one(
        {"_id": document["_id"]},
        {
            "$set": {
                "status": (
                    EmailDeliveryStatus.FAILED.value
                    if terminal
                    else EmailDeliveryStatus.RETRY.value
                ),
                "attempts": attempts,
                "next_attempt_at": None if terminal else now + timedelta(seconds=delay_seconds),
                "updated_at": now,
                "last_error": error,
            }
        },
    )


async def process_pending_email_deliveries(database, *, limit: int = MAX_BATCH_SIZE) -> int:
    settings_document = await get_email_settings_document(database)
    if not settings_document.get("enabled"):
        return 0

    now = _utcnow()
    cursor = database[EMAIL_DELIVERIES_COLLECTION].find(
        {
            "status": {
                "$in": [
                    EmailDeliveryStatus.QUEUED.value,
                    EmailDeliveryStatus.RETRY.value,
                ]
            },
            "$or": [
                {"next_attempt_at": {"$lte": now}},
                {"next_attempt_at": None},
            ],
        }
    ).sort("created_at", 1).limit(max(1, min(limit, 100)))
    deliveries = await cursor.to_list(None)
    sent_count = 0

    for document in deliveries:
        locked = await database[EMAIL_DELIVERIES_COLLECTION].find_one_and_update(
            {
                "_id": document["_id"],
                "status": document.get("status"),
            },
            {
                "$set": {
                    "status": EmailDeliveryStatus.SENDING.value,
                    "updated_at": _utcnow(),
                }
            },
        )
        if locked is None:
            continue

        message = OutboundEmail(
            recipient_email=document["recipient_email"],
            recipient_name=document.get("recipient_name"),
            subject=document.get("subject") or "DBAChum alert",
            text_content=document.get("text_content") or "DBAChum alert",
            html_content=document.get("html_content") or "<p>DBAChum alert</p>",
        )

        try:
            result = await send_email(settings_document, message, require_enabled=True)
        except Exception as exc:
            logger.warning(
                "Email delivery failed recipient=%s kind=%s: %s",
                document.get("recipient_email"),
                document.get("kind"),
                getattr(exc, "message", None) or exc,
            )
            await _mark_delivery_failure(database, document, exc)
            continue

        completed = _utcnow()
        attempts = int(document.get("attempts") or 0) + 1
        await database[EMAIL_DELIVERIES_COLLECTION].update_one(
            {"_id": document["_id"]},
            {
                "$set": {
                    "status": EmailDeliveryStatus.SENT.value,
                    "provider": result.provider,
                    "provider_message_id": result.message_id,
                    "attempts": attempts,
                    "next_attempt_at": None,
                    "sent_at": completed,
                    "updated_at": completed,
                    "last_error": None,
                }
            },
        )
        sent_count += 1

    return sent_count


async def send_test_email(
    database,
    *,
    recipient_email: str,
    recipient_name: str | None,
    requested_by: str,
) -> dict[str, Any]:
    settings_document = await get_email_settings_document(database)
    message = build_test_message(recipient_email, recipient_name)
    now = _utcnow()
    document = {
        "event_key": f"test:{uuid.uuid4()}",
        "kind": "test",
        "status": EmailDeliveryStatus.SENDING.value,
        "provider": str(settings_document.get("provider") or EmailProvider.BREVO.value),
        "recipient_email": recipient_email,
        "recipient_name": recipient_name,
        "subject": message.subject,
        "attempts": 0,
        "max_attempts": 1,
        "next_attempt_at": None,
        "created_at": now,
        "updated_at": now,
        "expires_at": _expires_at(now),
        "requested_by": requested_by,
    }
    result = await database[EMAIL_DELIVERIES_COLLECTION].insert_one(document)
    document["_id"] = result.inserted_id

    try:
        send_result = await send_email(
            settings_document,
            message,
            require_enabled=False,
        )
    except Exception as exc:
        await _mark_delivery_failure(database, document, exc)
        raise

    completed = _utcnow()
    await database[EMAIL_DELIVERIES_COLLECTION].update_one(
        {"_id": document["_id"]},
        {
            "$set": {
                "status": EmailDeliveryStatus.SENT.value,
                "provider": send_result.provider,
                "provider_message_id": send_result.message_id,
                "attempts": 1,
                "sent_at": completed,
                "updated_at": completed,
                "last_error": None,
            }
        },
    )
    return {
        "sent": True,
        "provider": send_result.provider,
        "recipient_email": recipient_email,
        "message_id": send_result.message_id,
    }


async def list_email_deliveries(database, *, limit: int = 50) -> list[EmailDeliveryResponse]:
    cursor = database[EMAIL_DELIVERIES_COLLECTION].find().sort("created_at", -1).limit(
        max(1, min(limit, 200))
    )
    documents = await cursor.to_list(None)
    return [_delivery_response(document) for document in documents]


async def retry_email_delivery(database, delivery_id: str) -> EmailDeliveryResponse:
    try:
        object_id = ObjectId(delivery_id)
    except Exception:
        raise AppError(
            "Email delivery record not found.",
            code="EMAIL_DELIVERY_NOT_FOUND",
            status_code=404,
        )

    now = _utcnow()
    result = await database[EMAIL_DELIVERIES_COLLECTION].update_one(
        {
            "_id": object_id,
            "status": EmailDeliveryStatus.FAILED.value,
        },
        {
            "$set": {
                "status": EmailDeliveryStatus.RETRY.value,
                "attempts": 0,
                "next_attempt_at": now,
                "updated_at": now,
                "last_error": None,
            }
        },
    )
    if result.matched_count == 0:
        document = await database[EMAIL_DELIVERIES_COLLECTION].find_one({"_id": object_id})
        if document is None:
            raise AppError(
                "Email delivery record not found.",
                code="EMAIL_DELIVERY_NOT_FOUND",
                status_code=404,
            )
        raise AppError(
            "Only failed email deliveries can be manually retried.",
            code="EMAIL_DELIVERY_NOT_FAILED",
            status_code=409,
        )

    document = await database[EMAIL_DELIVERIES_COLLECTION].find_one({"_id": object_id})
    return _delivery_response(document)


async def clear_email_deliveries(
    database,
    *,
    delivery_ids: list[str] | None = None,
    clear_all: bool = False,
) -> dict[str, int]:
    """Remove terminal delivery-history records only.

    Queued/retry/sending documents are intentionally preserved so clearing the
    status table cannot cancel mail that is still in-flight.
    """
    terminal_statuses = [
        EmailDeliveryStatus.SENT.value,
        EmailDeliveryStatus.FAILED.value,
    ]

    if clear_all:
        result = await database[EMAIL_DELIVERIES_COLLECTION].delete_many(
            {"status": {"$in": terminal_statuses}}
        )
        return {
            "deleted_count": int(result.deleted_count),
            "skipped_count": 0,
        }

    raw_ids = delivery_ids or []
    object_ids: list[ObjectId] = []
    for delivery_id in raw_ids:
        try:
            object_ids.append(ObjectId(delivery_id))
        except Exception as exc:
            raise AppError(
                "Email delivery record not found.",
                code="EMAIL_DELIVERY_NOT_FOUND",
                status_code=404,
            ) from exc

    if not object_ids:
        return {"deleted_count": 0, "skipped_count": 0}

    result = await database[EMAIL_DELIVERIES_COLLECTION].delete_many(
        {
            "_id": {"$in": object_ids},
            "status": {"$in": terminal_statuses},
        }
    )
    deleted_count = int(result.deleted_count)
    return {
        "deleted_count": deleted_count,
        "skipped_count": max(0, len(object_ids) - deleted_count),
    }
