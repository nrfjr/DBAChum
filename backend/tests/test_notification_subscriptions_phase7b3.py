from types import SimpleNamespace

import pytest
from bson import ObjectId

from app.schemas.notification import (
    NotificationCategory,
    NotificationEngine,
    NotificationScope,
    UserNotificationPreferences,
    UserNotificationPreferencesUpdate,
)
from app.services.notification_subscriptions import (
    category_for_alert,
    email_subscription_matches_alert,
)
from app.services import users


class FakeUsersCollection:
    def __init__(self, document):
        self.document = dict(document)

    async def find_one(self, query):
        if query.get("_id") == self.document.get("_id"):
            return dict(self.document)
        return None

    async def update_one(self, query, update):
        if query.get("_id") != self.document.get("_id"):
            return SimpleNamespace(matched_count=0)

        for key, value in update.get("$set", {}).items():
            if "." in key:
                first, second = key.split(".", 1)
                nested = self.document.setdefault(first, {})
                nested[second] = value
            else:
                self.document[key] = value

        return SimpleNamespace(matched_count=1)


class FakeDatabase:
    def __init__(self, document):
        self.users = FakeUsersCollection(document)


def base_user():
    return {
        "_id": ObjectId(),
        "username": "dba1",
        "display_name": "DBA One",
        "email": "dba1@example.com",
        "role": "operator",
        "is_active": True,
    }


def test_legacy_user_gets_safe_notification_defaults():
    result = users.user_to_response(base_user())

    assert result.notifications.email_enabled is False
    assert result.notifications.scope == NotificationScope.ALL
    assert set(result.notifications.severities) == {"critical", "warning"}
    assert NotificationEngine.ORACLE in result.notifications.engines
    assert result.notifications.include_servers is True
    assert result.notifications.include_system is True


@pytest.mark.asyncio
async def test_notification_update_merges_without_erasing_other_settings():
    document = base_user()
    document["notifications"] = UserNotificationPreferences(
        email_enabled=False,
        scope=NotificationScope.ALL,
        database_connection_ids=["old-db"],
    ).model_dump(mode="json")
    database = FakeDatabase(document)

    result = await users.update_current_user_notifications(
        database,
        str(document["_id"]),
        UserNotificationPreferencesUpdate(
            email_enabled=True,
            scope=NotificationScope.SELECTED,
            database_connection_ids=[" db1 ", "db1", "db2"],
        ),
    )

    assert result.notifications.email_enabled is True
    assert result.notifications.scope == NotificationScope.SELECTED
    assert result.notifications.database_connection_ids == ["db1", "db2"]
    assert NotificationEngine.SQLSERVER in result.notifications.engines
    assert NotificationCategory.AVAILABILITY in result.notifications.categories


def test_alert_categories_are_stable_for_current_rule_families():
    assert category_for_alert("availability", "database") == NotificationCategory.AVAILABILITY
    assert category_for_alert("sqlserver:database_state", "database") == NotificationCategory.AVAILABILITY
    assert category_for_alert("blocking_sessions", "database") == NotificationCategory.BLOCKING
    assert category_for_alert("tablespace:USERS", "database") == NotificationCategory.STORAGE
    assert category_for_alert("filesystem:/u01", "server") == NotificationCategory.STORAGE
    assert category_for_alert("sqlserver:agent_failures", "database") == NotificationCategory.JOBS
    assert category_for_alert("future:backup_sla", "database") == NotificationCategory.BACKUP
    assert category_for_alert("heartbeat", "collector") == NotificationCategory.SYSTEM
    assert category_for_alert("cpu_pressure", "server") == NotificationCategory.PERFORMANCE


def test_database_subscription_respects_severity_category_engine_and_selected_scope():
    subscription = UserNotificationPreferences(
        email_enabled=True,
        severities=["critical"],
        categories=["availability"],
        engines=["oracle"],
        scope="selected",
        database_connection_ids=["db1"],
        include_servers=False,
        include_system=False,
    )

    alert = {
        "source_type": "database",
        "source_id": "db1",
        "rule_key": "availability",
        "severity": "critical",
    }

    assert email_subscription_matches_alert(
        subscription,
        alert,
        source_engine="oracle",
    )
    assert not email_subscription_matches_alert(
        subscription,
        alert,
        source_engine="sqlserver",
    )

    other_source = {**alert, "source_id": "db2"}
    assert not email_subscription_matches_alert(
        subscription,
        other_source,
        source_engine="oracle",
    )

    warning = {**alert, "severity": "warning"}
    assert not email_subscription_matches_alert(
        subscription,
        warning,
        source_engine="oracle",
    )


def test_server_and_system_subscription_switches_are_independent():
    subscription = UserNotificationPreferences(
        email_enabled=True,
        include_servers=True,
        include_system=False,
        scope="selected",
        server_ids=["srv1"],
    )

    server_alert = {
        "source_type": "server",
        "source_id": "srv1",
        "rule_key": "cpu_pressure",
        "severity": "warning",
    }
    collector_alert = {
        "source_type": "collector",
        "source_id": "primary",
        "rule_key": "heartbeat",
        "severity": "critical",
    }

    assert email_subscription_matches_alert(subscription, server_alert)
    assert not email_subscription_matches_alert(subscription, collector_alert)


def test_missing_database_engine_fails_closed_for_delivery_matching():
    subscription = UserNotificationPreferences(email_enabled=True)
    alert = {
        "source_type": "database",
        "source_id": "db1",
        "rule_key": "availability",
        "severity": "critical",
    }

    assert not email_subscription_matches_alert(subscription, alert)
