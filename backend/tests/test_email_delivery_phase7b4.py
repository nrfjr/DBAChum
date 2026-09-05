from datetime import datetime, timezone
from pathlib import Path

from app.core.permissions import Permission, permission_values_for_role
from app.schemas.user import UserRole
from app.services.email_delivery import should_enqueue_alert_email
from app.services.email_settings import email_settings_to_response
from app.services.email_transport import build_test_message


def test_email_delivery_permission_is_admin_only():
    viewer = set(permission_values_for_role(UserRole.VIEWER))
    operator = set(permission_values_for_role(UserRole.OPERATOR))
    admin = set(permission_values_for_role(UserRole.ADMIN))

    assert Permission.NOTIFICATION_MANAGE.value not in viewer
    assert Permission.NOTIFICATION_MANAGE.value not in operator
    assert Permission.NOTIFICATION_MANAGE.value in admin


def test_alert_email_only_fires_on_activation_or_escalation():
    now = datetime.now(timezone.utc)
    active_warning = {
        "status": "active",
        "severity": "warning",
        "first_seen_at": now,
    }
    active_critical = {
        **active_warning,
        "severity": "critical",
    }

    assert should_enqueue_alert_email(
        {"status": "pending", "severity": "warning"},
        active_warning,
    )
    assert not should_enqueue_alert_email(active_warning, active_warning)
    assert should_enqueue_alert_email(active_warning, active_critical)
    assert not should_enqueue_alert_email(active_critical, active_warning)
    assert not should_enqueue_alert_email(
        {"status": "active", "severity": "warning"},
        {**active_warning, "status": "resolved"},
    )


def test_email_settings_response_never_returns_provider_secrets():
    response = email_settings_to_response(
        {
            "_id": "email",
            "enabled": True,
            "provider": "brevo",
            "sender_name": "DBAChum Alerts",
            "sender_email": "alerts@example.com",
            "brevo_api_key_encrypted": "secret-ciphertext",
            "smtp_password_encrypted": "another-secret-ciphertext",
        }
    )

    payload = response.model_dump(mode="json")
    assert payload["has_brevo_api_key"] is True
    assert payload["has_smtp_password"] is True
    assert "brevo_api_key" not in payload
    assert "smtp_password" not in payload
    assert "secret-ciphertext" not in str(payload)


def test_test_message_accepts_external_recipient_without_domain_policy():
    message = build_test_message(
        "outside.user@example.net",
        "External DBA",
    )

    assert message.recipient_email == "outside.user@example.net"
    assert "DBAChum email delivery" in message.subject
    assert "outside.user@example.net" in message.text_content


def test_notification_delivery_routes_use_admin_permission_boundary():
    endpoint = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "api"
        / "v1"
        / "endpoints"
        / "notification_delivery.py"
    ).read_text(encoding="utf-8")

    assert endpoint.count("Permission.NOTIFICATION_MANAGE") == 5
