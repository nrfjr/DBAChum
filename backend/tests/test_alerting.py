from datetime import datetime, timezone

from app.services.alerting import (
    AlertCondition,
    database_alert_conditions,
    server_alert_conditions,
    transition_alert,
)


def now():
    return datetime(2026, 8, 30, 6, 0, tzinfo=timezone.utc)


def test_alert_requires_persistence_before_becoming_active():
    condition = AlertCondition(
        rule_key="availability",
        active=True,
        severity="critical",
        title="DB down",
        message="No connection",
        required_samples=2,
        recovery_samples=2,
    )

    action, first = transition_alert(None, condition, now())
    assert action == "update"
    assert first["status"] == "pending"
    assert first["bad_count"] == 1

    existing = {"status": "pending", "bad_count": 1}
    action, second = transition_alert(existing, condition, now())
    assert action == "update"
    assert second["status"] == "active"
    assert second["bad_count"] == 2


def test_cleared_active_alert_stays_suppressed_until_recovery():
    bad = AlertCondition(
        rule_key="filesystem:/arch",
        active=True,
        severity="critical",
        title="/arch full",
        message="95%",
        recovery_samples=2,
    )
    existing = {"status": "cleared", "good_count": 0}
    action, change = transition_alert(existing, bad, now())
    assert action == "update"
    assert "status" not in change

    recovered = AlertCondition(
        rule_key=bad.rule_key,
        active=False,
        severity=bad.severity,
        title=bad.title,
        message=bad.message,
        recovery_samples=2,
    )
    action, change = transition_alert(existing, recovered, now())
    assert action == "update"
    assert change == {"good_count": 1}

    existing = {"status": "cleared", "good_count": 1}
    action, change = transition_alert(existing, recovered, now())
    assert action == "delete"
    assert change is None


def test_database_rules_include_unreachable_and_blocking():
    connection = {"_id": "db1", "name": "RMSPRD"}
    sample = {
        "status": "online",
        "blocked": 3,
        "active": 5,
        "oracle": {},
    }
    rules = {item.rule_key: item for item in database_alert_conditions(connection, sample)}
    assert rules["availability"].active is False
    assert rules["blocking_sessions"].active is True
    assert rules["blocking_sessions"].severity == "warning"


def test_server_filesystem_thresholds_are_evaluated_per_mount():
    server = {"_id": "s1", "name": "DB01"}
    sample = {
        "status": "online",
        "cpu_used_percent": 10,
        "memory": {"used_percent": 40},
        "filesystems": [
            {
                "filesystem": "/dev/mapper/vg-arch",
                "mount_point": "/arch",
                "used_percent": 92,
            }
        ],
    }
    rules = {item.rule_key: item for item in server_alert_conditions(server, sample)}
    assert rules["filesystem:/arch"].active is True
    assert rules["filesystem:/arch"].severity == "critical"
