from datetime import datetime, timezone

import pytest

from app.services import metrics_collector
from app.services.alerting import database_alert_conditions
from app.schemas.mysql_dba import MySqlHealthResponse


def mysql_health_snapshot(
    *,
    slow_queries=10,
    questions=100,
    threads_created=5,
    connections_total=50,
    aborted_connects=2,
    aborted_clients=1,
    tmp_tables=20,
    tmp_disk=4,
    current_connections=3,
    max_connections=100,
    running=2,
    blocked=0,
    longest=12,
    long_running=0,
):
    return {
        "checked_at": datetime.now(timezone.utc),
        "database_name": "test",
        "scope": "database",
        "product": "MariaDB",
        "generation": "10.4",
        "performance_schema_enabled": True,
        "processlist_source": "information_schema.processlist",
        "connections": {
            "current": current_connections,
            "maximum": max_connections,
            "utilization_percent": round(current_connections / max_connections * 100, 2),
            "max_used": 8,
            "max_used_percent": 8.0,
            "total_since_startup": connections_total,
            "aborted_connects": aborted_connects,
            "aborted_clients": aborted_clients,
        },
        "workload": {
            "threads_running": running,
            "slow_queries": slow_queries,
            "questions": questions,
            "longest_active_seconds": longest,
            "long_running_sessions": long_running,
            "long_running_threshold_seconds": 60,
            "threads_created": threads_created,
        },
        "innodb": {
            "active_transactions": 1,
            "blocked_transactions": blocked,
            "oldest_transaction_seconds": 4,
            "buffer_pool_size_bytes": 1024,
            "buffer_pool_data_bytes": 768,
            "buffer_pool_used_percent": 75.0,
        },
        "temporary_tables": {
            "created": tmp_tables,
            "created_on_disk": tmp_disk,
            "disk_percent": round(tmp_disk / tmp_tables * 100, 2),
        },
        "server": {
            "uptime_seconds": 1000,
            "read_only": False,
            "slow_query_log": True,
            "long_query_time_seconds": 10.0,
        },
        "warnings": [],
    }


def test_mysql_health_schema_preserves_long_running_fields():
    payload = mysql_health_snapshot(longest=90, long_running=2)
    response = MySqlHealthResponse.model_validate({"available": True, **payload})
    assert response.workload.long_running_sessions == 2
    assert response.workload.long_running_threshold_seconds == 60


def test_mysql_counter_deltas_use_baseline_then_interval_values():
    state = metrics_collector.CollectorDeltaState()

    first = metrics_collector._mysql_counter_deltas(
        state,
        "mysql-1",
        mysql_health_snapshot(),
    )
    assert first["baseline"] is True
    assert first["slow_queries_delta"] is None
    assert first["temporary_disk_percent_interval"] is None

    second = metrics_collector._mysql_counter_deltas(
        state,
        "mysql-1",
        mysql_health_snapshot(
            slow_queries=13,
            questions=145,
            threads_created=6,
            connections_total=55,
            aborted_connects=4,
            aborted_clients=2,
            tmp_tables=30,
            tmp_disk=7,
        ),
    )
    assert second["baseline"] is False
    assert second["slow_queries_delta"] == 3
    assert second["questions_delta"] == 45
    assert second["threads_created_delta"] == 1
    assert second["connections_total_delta"] == 5
    assert second["aborted_connects_delta"] == 2
    assert second["aborted_clients_delta"] == 1
    assert second["temporary_tables_delta"] == 10
    assert second["temporary_disk_tables_delta"] == 3
    assert second["temporary_disk_percent_interval"] == 30.0


def test_mysql_counter_reset_avoids_false_delta_after_server_restart():
    state = metrics_collector.CollectorDeltaState()
    metrics_collector._mysql_counter_deltas(
        state,
        "mysql-1",
        mysql_health_snapshot(slow_queries=100),
    )
    second = metrics_collector._mysql_counter_deltas(
        state,
        "mysql-1",
        mysql_health_snapshot(slow_queries=2),
    )
    assert second["slow_queries_delta"] is None

    state.reset_connection("mysql-1")
    third = metrics_collector._mysql_counter_deltas(
        state,
        "mysql-1",
        mysql_health_snapshot(slow_queries=3),
    )
    assert third["baseline"] is True
    assert third["slow_queries_delta"] is None


def test_compact_mysql_health_keeps_native_units_and_storage_summary():
    state = metrics_collector.CollectorDeltaState()
    health = mysql_health_snapshot(current_connections=80, max_connections=100)
    deltas = metrics_collector._mysql_counter_deltas(state, "mysql-1", health)
    storage = metrics_collector._compact_mysql_storage(
        {
            "checked_at": datetime.now(timezone.utc),
            "scope": "database",
            "database_name": "test",
            "data_bytes": 1000,
            "index_bytes": 250,
            "total_bytes": 1250,
            "table_count": 8,
            "schema_count": 1,
            "warnings": [],
        }
    )
    compact = metrics_collector._compact_mysql_health(health, deltas, storage)

    assert compact["connection_utilization_percent"] == 80.0
    assert compact["threads_running"] == 2
    assert compact["blocked_transactions"] == 0
    assert compact["buffer_pool_used_percent"] == 75.0
    assert compact["storage"]["total_bytes"] == 1250


@pytest.mark.asyncio
async def test_mysql_collector_enriches_overview_and_calculates_deltas(monkeypatch):
    connection = {
        "_id": "mysql-1",
        "engine": "mysql",
        "name": "MariaDB test",
        "host": "db01",
        "port": 3306,
        "database": "test",
    }
    state = metrics_collector.CollectorDeltaState()
    health_calls = 0

    async def fake_overview(_connection):
        return {
            "connection_id": "mysql-1",
            "engine": "mysql",
            "status": "online",
            "response_time_ms": 2.5,
            "active": 1,
            "connections": 2,
            "blocked": 0,
            "uptime_seconds": 1000,
            "warnings": [],
            "error": None,
        }

    async def fake_health(_connection):
        nonlocal health_calls
        health_calls += 1
        if health_calls == 1:
            return mysql_health_snapshot()
        return mysql_health_snapshot(
            slow_queries=12,
            questions=125,
            connections_total=53,
            aborted_connects=3,
            tmp_tables=25,
            tmp_disk=5,
            running=4,
            current_connections=5,
            blocked=1,
            long_running=1,
            longest=80,
        )

    async def fake_storage(_connection):
        return {
            "checked_at": datetime.now(timezone.utc),
            "scope": "database",
            "database_name": "test",
            "data_bytes": 1000,
            "index_bytes": 200,
            "total_bytes": 1200,
            "table_count": 6,
            "schema_count": 1,
            "warnings": [],
        }

    monkeypatch.setattr(metrics_collector, "collect_database_overview", fake_overview)
    monkeypatch.setattr(metrics_collector, "get_mysql_health", fake_health)
    monkeypatch.setattr(metrics_collector, "get_mysql_storage", fake_storage)

    first = await metrics_collector._collect_database_sample(None, connection, state)
    assert first["mysql"]["baseline"] is True
    assert first["mysql"]["slow_queries_delta"] is None
    assert first["mysql"]["storage"]["total_bytes"] == 1200

    second = await metrics_collector._collect_database_sample(None, connection, state)
    assert second["active"] == 4
    assert second["connections"] == 5
    assert second["blocked"] == 1
    assert second["mysql"]["slow_queries_delta"] == 2
    assert second["mysql"]["questions_delta"] == 25
    assert second["mysql"]["connections_total_delta"] == 3
    assert second["mysql"]["aborted_connects_delta"] == 1
    assert second["mysql"]["long_running_sessions"] == 1


def test_mysql_instance_alert_owner_is_one_connection_per_host_port():
    connections = [
        {"_id": "a", "engine": "mysql", "host": "DB01", "port": 3306},
        {"_id": "b", "engine": "mysql", "host": "db01", "port": 3306},
        {"_id": "c", "engine": "mysql", "host": "db02", "port": 3306},
        {"_id": "s", "engine": "sqlserver", "host": "db01", "port": 1433},
    ]
    assert metrics_collector._mysql_instance_alert_owners(connections) == {"a", "c"}


def test_mysql_instance_alert_owner_prefers_healthy_connection():
    connections = [
        {"_id": "a", "engine": "mysql", "host": "db01", "port": 3306},
        {"_id": "b", "engine": "mysql", "host": "db01", "port": 3306},
    ]
    samples = [{"status": "unreachable"}, {"status": "online"}]
    assert metrics_collector._mysql_instance_alert_owners(connections, samples) == {"b"}


def test_mysql_alerts_cover_connection_pressure_and_deduplicate_instance_rules(monkeypatch):
    connection = {
        "_id": "mysql-1",
        "name": "MariaDB",
        "engine": "mysql",
        "host": "db01",
        "port": 3306,
    }
    sample = {
        "status": "online",
        "active": 90,
        "blocked": 2,
        "mysql": {
            "threads_running": 90,
            "blocked_transactions": 2,
            "connections_current": 92,
            "connections_maximum": 100,
            "connection_utilization_percent": 92.0,
            "longest_active_seconds": 180,
            "long_running_sessions": 1,
            "processlist_source": "information_schema.processlist",
        },
    }

    rules = {item.rule_key: item for item in database_alert_conditions(connection, sample)}
    assert rules["blocking_sessions"].active is True
    assert rules["mysql:connection_utilization"].active is True
    assert rules["mysql:connection_utilization"].severity == "critical"

    suppressed = {
        item.rule_key: item
        for item in database_alert_conditions(
            connection,
            sample,
            include_mysql_instance_conditions=False,
        )
    }
    assert suppressed["blocking_sessions"].active is False
    assert suppressed["active_sessions"].active is False
    assert suppressed["mysql:connection_utilization"].active is False
    assert suppressed["mysql:connection_utilization"].context["deduplicated"] is True

    monkeypatch.setattr(
        metrics_collector.settings,
        "alert_mysql_long_running_seconds",
        120,
    )
    long_rules = {
        item.rule_key: item
        for item in database_alert_conditions(connection, sample)
    }
    assert long_rules["mysql:long_running"].active is True
    assert long_rules["mysql:long_running"].threshold == 120
