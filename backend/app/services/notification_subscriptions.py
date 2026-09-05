from __future__ import annotations

from typing import Any

from app.schemas.notification import (
    NotificationCategory,
    NotificationEngine,
    NotificationScope,
    UserNotificationPreferences,
)


def category_for_alert(
    rule_key: str,
    source_type: str,
) -> NotificationCategory:


    rule = str(rule_key or "").strip().lower()
    source = str(source_type or "").strip().lower()

    if source == "collector" or rule == "heartbeat":
        return NotificationCategory.SYSTEM

    if rule in {"availability", "sqlserver:database_state"}:
        return NotificationCategory.AVAILABILITY

    if rule == "blocking_sessions" or "blocking" in rule:
        return NotificationCategory.BLOCKING

    if (
        rule.startswith("tablespace:")
        or rule.startswith("filesystem:")
        or rule in {
            "fra_usage",
            "sqlserver:transaction_log",
            "sqlserver:tempdb",
        }
    ):
        return NotificationCategory.STORAGE

    if rule in {
        "sqlserver:agent_failures",
    }:
        return NotificationCategory.JOBS

    if "backup" in rule:
        return NotificationCategory.BACKUP

    return NotificationCategory.PERFORMANCE


def email_subscription_matches_alert(
    subscription: UserNotificationPreferences,
    alert: dict[str, Any],
    *,
    source_engine: str | None = None,
) -> bool:

    if not subscription.email_enabled:
        return False

    severity = str(alert.get("severity") or "").lower()
    if severity not in {
        item.value
        for item in subscription.severities
    }:
        return False

    category = category_for_alert(
        str(alert.get("rule_key") or ""),
        str(alert.get("source_type") or ""),
    )
    if category not in subscription.categories:
        return False

    source_type = str(
        alert.get("source_type") or ""
    ).lower()
    source_id = str(alert.get("source_id") or "")

    if source_type == "collector":
        return subscription.include_system

    if source_type == "server":
        if not subscription.include_servers:
            return False
        if subscription.scope == NotificationScope.SELECTED:
            return source_id in subscription.server_ids
        return True

    if source_type != "database":
        return False

    engine_value = (
        source_engine
        or alert.get("source_engine")
    )
    if not engine_value:
        return False

    try:
        engine = NotificationEngine(
            str(engine_value).lower()
        )
    except ValueError:
        return False

    if engine not in subscription.engines:
        return False

    if subscription.scope == NotificationScope.SELECTED:
        return source_id in subscription.database_connection_ids

    return True
