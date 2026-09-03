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


def test_sqlserver_operational_alerts_use_health_snapshot():
    connection = {"_id": "db2", "name": "ERP SQL", "engine": "sqlserver"}
    sample = {
        "status": "online",
        "blocked": 0,
        "active": 4,
        "sqlserver": {
            "database_state": "ONLINE",
            "recovery_model": "FULL",
            "log_reuse_wait": "LOG_BACKUP",
            "log_size_bytes": 10_000,
            "log_used_percent": 95.0,
            "tempdb_allocated_bytes": 20_000,
            "tempdb_used_percent": 20.0,
            "agent_available": True,
            "agent_failed_jobs": 1,
            "failed_jobs": [{"name": "Nightly backup", "status": "failed"}],
        },
    }
    rules = {item.rule_key: item for item in database_alert_conditions(connection, sample)}
    assert rules["sqlserver:database_state"].active is False
    assert rules["sqlserver:transaction_log"].active is True
    assert rules["sqlserver:transaction_log"].severity == "critical"
    assert rules["sqlserver:agent_failures"].active is True
    assert rules["sqlserver:tempdb"].active is False


def test_sqlserver_database_state_alert_is_immediate():
    connection = {"_id": "db3", "name": "Legacy", "engine": "sqlserver"}
    sample = {
        "status": "online",
        "blocked": 0,
        "active": 0,
        "sqlserver": {"database_state": "SUSPECT"},
    }
    rules = {item.rule_key: item for item in database_alert_conditions(connection, sample)}
    state = rules["sqlserver:database_state"]
    assert state.active is True
    assert state.severity == "critical"
    assert state.required_samples == 1
