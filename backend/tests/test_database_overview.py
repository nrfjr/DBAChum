import pytest

from app.core.exceptions import AppError
from app.services import database_overview


def make_connection(
    *,
    engine="oracle",
    enabled=True,
):
    return {
        "_id": "connection-1",
        "engine": engine,
        "enabled": enabled,
    }


@pytest.mark.asyncio
async def test_disabled_connection_skips_connector(
    monkeypatch,
):
    async def should_not_run(_connection):
        raise AssertionError(
            "Disabled connections must not be opened."
        )

    monkeypatch.setattr(
        database_overview,
        "get_oracle_overview",
        should_not_run,
    )

    result = await (
        database_overview
        .collect_database_overview(
            make_connection(enabled=False)
        )
    )

    assert result["status"] == "disabled"
    assert result["warnings"] == []
    assert result["connection_id"] == "connection-1"
    assert result["engine"] == "oracle"


@pytest.mark.asyncio
async def test_unsupported_engine_is_unreachable():
    result = await (
        database_overview
        .collect_database_overview(
            make_connection(engine="postgresql")
        )
    )

    assert result["status"] == "unreachable"
    assert (
        result["error"]
        == "Unsupported database engine: postgresql"
    )
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_connector_app_error_becomes_unreachable(
    monkeypatch,
):
    async def fail_connection(_connection):
        raise AppError(
            "Database refused the connection.",
            code="ORACLE_MONITORING_FAILED",
        )

    monkeypatch.setattr(
        database_overview,
        "get_oracle_overview",
        fail_connection,
    )

    result = await (
        database_overview
        .collect_database_overview(
            make_connection()
        )
    )

    assert result["status"] == "unreachable"
    assert (
        result["error"]
        == "Database refused the connection."
    )
    assert result["warnings"] == []


@pytest.mark.asyncio
async def test_connector_warnings_mark_overview_limited(
    monkeypatch,
):
    async def limited_overview(_connection):
        return {
            "active": None,
            "connections": 5,
            "blocked": 0,
            "warnings": [
                "Active sessions unavailable."
            ],
        }

    monkeypatch.setattr(
        database_overview,
        "get_oracle_overview",
        limited_overview,
    )

    result = await (
        database_overview
        .collect_database_overview(
            make_connection()
        )
    )

    assert result["status"] == "limited"
    assert result["connections"] == 5
    assert result["blocked"] == 0
    assert result["active"] is None
    assert result["warnings"] == [
        "Active sessions unavailable."
    ]


@pytest.mark.asyncio
async def test_unexpected_connector_error_does_not_break_monitoring(
    monkeypatch,
):
    async def unexpected_failure(_connection):
        raise RuntimeError(
            "driver exploded with internal details"
        )

    monkeypatch.setattr(
        database_overview,
        "get_oracle_overview",
        unexpected_failure,
    )

    result = await (
        database_overview
        .collect_database_overview(
            make_connection()
        )
    )

    assert result["status"] == "unreachable"
    assert (
        result["error"]
        == "Monitoring failed unexpectedly."
    )
    assert "internal details" not in result["error"]
    assert result["warnings"] == []


class FakeOverviewCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *_args):
        return self

    async def to_list(self, _length):
        return list(self.items)


class FakeOverviewConnections:
    def __init__(self, items):
        self.items = items
        self.last_query = None

    def find(self, query):
        self.last_query = query
        return FakeOverviewCursor(self.items)


class FakeOverviewDatabase:
    def __init__(self, connections):
        self.database_connections = (
            FakeOverviewConnections(connections)
        )


@pytest.mark.asyncio
async def test_overview_list_survives_one_unexpected_failure(
    monkeypatch,
):
    database = FakeOverviewDatabase(
        [
            make_connection(engine="oracle"),
            {
                "_id": "connection-2",
                "engine": "mysql",
                "enabled": True,
            },
        ]
    )

    async def oracle_overview(_connection):
        return {
            "active": 2,
            "connections": 4,
            "blocked": 0,
            "warnings": [],
        }

    async def mysql_overview(_connection):
        raise RuntimeError("unexpected driver failure")

    monkeypatch.setattr(
        database_overview,
        "get_oracle_overview",
        oracle_overview,
    )
    monkeypatch.setattr(
        database_overview,
        "get_mysql_overview",
        mysql_overview,
    )

    result = await (
        database_overview
        .list_database_overviews(database)
    )

    assert (
        database
        .database_connections
        .last_query
        == {"enabled": True}
    )
    assert len(result) == 2
    assert result[0]["status"] == "online"
    assert result[0]["active"] == 2
    assert result[1]["status"] == "unreachable"
    assert (
        result[1]["error"]
        == "Monitoring failed unexpectedly."
    )
