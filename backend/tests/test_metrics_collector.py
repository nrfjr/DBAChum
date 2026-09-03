from app.services.metrics_collector import _sqlserver_instance_alert_owners
from datetime import datetime, timedelta, timezone

import pytest

from app.core.collections import METRICS_COLLECTION_NAME, telemetry_retention_seconds
from app.services import metrics_collector


class FakeCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *_args):
        return self

    async def to_list(self, _length):
        return list(self.items)


class FakeConnectionsCollection:
    def __init__(self, items):
        self.items = items
        self.last_query = None

    def find(self, query):
        self.last_query = query
        return FakeCursor(self.items)


class FakeInsertManyResult:
    def __init__(self, inserted_count):
        self.inserted_ids = list(range(inserted_count))


class FakeMetricsCollection:
    def __init__(self):
        self.inserted = []

    async def insert_many(self, documents):
        self.inserted.extend(documents)
        return FakeInsertManyResult(len(documents))


class FakeDatabase:
    def __init__(self, connections):
        self.database_connections = FakeConnectionsCollection(connections)
        self.metric_samples = FakeMetricsCollection()

    def __getitem__(self, name):
        assert name == METRICS_COLLECTION_NAME
        return self.metric_samples


def test_telemetry_retention_is_fixed_to_24_hours():
    assert telemetry_retention_seconds() == 24 * 60 * 60


def test_build_metric_sample_preserves_zero_and_null():
    checked_at = datetime.now(timezone.utc)
    sample = metrics_collector.build_metric_sample(
        {
            "connection_id": "connection-1",
            "engine": "oracle",
            "checked_at": checked_at,
            "status": "online",
            "response_time_ms": 125.5,
            "active": 0,
            "connections": None,
            "blocked": 0,
            "uptime_seconds": 3600,
            "warnings": [],
            "error": None,
        }
    )
    assert sample["meta"] == {
        "connection_id": "connection-1",
        "engine": "oracle",
    }
    assert sample["checked_at"] == checked_at
    assert sample["active"] == 0
    assert sample["connections"] is None
    assert sample["blocked"] == 0
    assert sample["collected_at"].utcoffset().total_seconds() == 0


def test_counter_deltas_become_baseline_after_reset():
    state = metrics_collector.CollectorDeltaState()
    first = metrics_collector._system_deltas(
        state,
        "db1",
        {
            "CPU used by this session": 1000,
            "execute count": 20,
        },
    )
    assert first["cpu_time_seconds"] is None
    assert first["execute_count"] is None

    second = metrics_collector._system_deltas(
        state,
        "db1",
        {
            "CPU used by this session": 1125,
            "execute count": 27,
        },
    )
    assert second["cpu_time_seconds"] == 1.25
    assert second["execute_count"] == 7

    state.reset_connection("db1")
    third = metrics_collector._system_deltas(
        state,
        "db1",
        {
            "CPU used by this session": 1200,
            "execute count": 30,
        },
    )
    assert third["cpu_time_seconds"] is None
    assert third["execute_count"] is None


def test_server_due_uses_slower_server_interval(monkeypatch):
    state = metrics_collector.CollectorDeltaState()
    now = datetime.now(timezone.utc)
    assert state.server_due("server-1", now)
    state.last_server_at["server-1"] = now
    assert not state.server_due("server-1", now + timedelta(seconds=10))


@pytest.mark.asyncio
async def test_collect_database_metrics_once_for_non_oracle(monkeypatch):
    database = FakeDatabase(
        [
            {"_id": "one", "engine": "mysql"},
            {"_id": "two", "engine": "sqlserver"},
        ]
    )

    async def fake_collect(connection):
        return {
            "connection_id": str(connection["_id"]),
            "engine": connection["engine"],
            "status": "online",
            "active": 1,
            "connections": 2,
            "blocked": 0,
            "warnings": [],
            "error": None,
        }

    monkeypatch.setattr(
        metrics_collector,
        "collect_database_overview",
        fake_collect,
    )

    result = await metrics_collector.collect_database_metrics_once(
        database,
        metrics_collector.CollectorDeltaState(),
    )

    assert (
        database.database_connections.last_query
        == metrics_collector.monitored_connections_filter()
    )
    assert result.target_count == 2
    assert result.inserted_count == 2
    assert result.online_count == 2
    assert result.failed_count == 0
    assert len(database.metric_samples.inserted) == 2


def test_sqlserver_health_due_uses_operational_interval():
    state = metrics_collector.CollectorDeltaState()
    now = datetime.now(timezone.utc)
    assert state.sqlserver_health_due("sql-1", now)
    state.last_sqlserver_health_at["sql-1"] = now
    assert not state.sqlserver_health_due("sql-1", now + timedelta(seconds=10))


def test_sqlserver_instance_alert_owner_is_one_connection_per_host_port():
    connections = [
        {"_id": "a", "engine": "sqlserver", "host": "DB01", "port": 1433},
        {"_id": "b", "engine": "sqlserver", "host": "db01", "port": 1433},
        {"_id": "c", "engine": "sqlserver", "host": "db02", "port": 1433},
        {"_id": "o", "engine": "oracle", "host": "db01", "port": 1521},
    ]
    assert _sqlserver_instance_alert_owners(connections) == {"a", "c"}


def test_sqlserver_instance_alert_owner_prefers_healthy_connection():
    connections = [
        {"_id": "a", "engine": "sqlserver", "host": "db01", "port": 1433},
        {"_id": "b", "engine": "sqlserver", "host": "db01", "port": 1433},
    ]
    samples = [
        {"status": "unreachable"},
        {"status": "online"},
    ]
    assert _sqlserver_instance_alert_owners(connections, samples) == {"b"}
