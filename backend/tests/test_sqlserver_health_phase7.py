from datetime import datetime

from app.connectors.sqlserver_health import (
    _agent_datetime,
    _agent_status,
    _duration_seconds,
)
from app.services.metrics_collector import _compact_sqlserver_health


def test_sql_agent_duration_supports_more_than_24_hours():
    assert _duration_seconds(250102) == 25 * 3600 + 60 + 2


def test_sql_agent_datetime_is_server_local_not_fake_utc():
    value = _agent_datetime(20260903, 143205)
    assert value == datetime(2026, 9, 3, 14, 32, 5)
    assert value.tzinfo is None


def test_sql_agent_status_mapping():
    assert _agent_status(0) == "failed"
    assert _agent_status(1) == "succeeded"
    assert _agent_status(None) == "never_run"


def test_collector_compacts_health_without_storing_full_job_history():
    compact = _compact_sqlserver_health(
        {
            "checked_at": datetime(2026, 9, 3, 2, 0),
            "database_name": "ERP",
            "generation": "SQL Server 2022",
            "database": {
                "state": "ONLINE",
                "recovery_model": "FULL",
                "log_reuse_wait": "NOTHING",
            },
            "transaction_log": {
                "size_bytes": 1000,
                "used_bytes": 800,
                "used_percent": 80.0,
            },
            "workload": {
                "blocked": 1,
                "long_running": 2,
                "longest_request_ms": 420000,
                "long_running_threshold_seconds": 300,
            },
            "tempdb": {
                "allocated_bytes": 2000,
                "used_bytes": 1000,
                "used_percent": 50.0,
            },
            "agent": {
                "available": True,
                "enabled_jobs": 3,
                "failed_jobs": 1,
                "running_jobs": 0,
                "jobs": [
                    {"name": "Backup", "enabled": True, "last_status": "failed"},
                    {"name": "Old disabled", "enabled": False, "last_status": "failed"},
                    {"name": "Stats", "enabled": True, "last_status": "succeeded"},
                ],
            },
            "warnings": [],
        }
    )
    assert compact["database_state"] == "ONLINE"
    assert compact["log_used_percent"] == 80.0
    assert compact["agent_failed_jobs"] == 1
    assert [item["name"] for item in compact["failed_jobs"]] == ["Backup"]
    assert "jobs" not in compact
