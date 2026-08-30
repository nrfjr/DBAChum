from datetime import datetime, timezone

import pytest

from app.core.collections import (
    METRICS_COLLECTION_NAME,
    ORACLE_SQL_TEXT_COLLECTION_NAME,
)
from app.services import database_metrics


class FakeHistoryCursor:
    def __init__(
        self,
        items,
    ):
        self.items = items

        self.sort_args = None
        self.limit_value = None

    def sort(
        self,
        *args,
    ):
        self.sort_args = args

        return self

    def limit(
        self,
        value,
    ):
        self.limit_value = value

        return self

    async def to_list(
        self,
        _length,
    ):
        return list(
            self.items[
                :self.limit_value
            ]
        )


class FakeHistoryCollection:
    def __init__(
        self,
        items,
    ):
        self.items = items

        self.last_filter = None
        self.last_projection = None
        self.cursor = None

    def find(
        self,
        query,
        projection,
    ):
        self.last_filter = query
        self.last_projection = (
            projection
        )

        self.cursor = (
            FakeHistoryCursor(
                self.items
            )
        )

        return self.cursor


class FakeDatabase:
    def __init__(
        self,
        items,
        sql_texts=None,
    ):
        self.history = (
            FakeHistoryCollection(
                items
            )
        )
        self.sql_texts = (
            FakeHistoryCollection(
                sql_texts or []
            )
        )

    def __getitem__(
        self,
        name,
    ):
        if name == METRICS_COLLECTION_NAME:
            return self.history
        if name == ORACLE_SQL_TEXT_COLLECTION_NAME:
            return self.sql_texts
        raise AssertionError(name)


@pytest.mark.asyncio
async def test_history_is_returned_oldest_to_newest(
    monkeypatch,
):
    connection_id = (
        "connection-1"
    )

    newer = {
        "collected_at":
            datetime(
                2026,
                8,
                17,
                12,
                2,
                tzinfo=timezone.utc,
            ),

        "status":
            "online",

        "active":
            3,
    }

    older = {
        "collected_at":
            datetime(
                2026,
                8,
                17,
                12,
                1,
                tzinfo=timezone.utc,
            ),

        "status":
            "online",

        "active":
            2,
    }

    database = FakeDatabase(
        [
            newer,
            older,
        ]
    )

    async def fake_get_connection(
        _database,
        requested_id,
    ):
        assert (
            requested_id
            == connection_id
        )

        return {
            "engine":
                "oracle",
        }

    monkeypatch.setattr(
        database_metrics,
        "get_database_connection",
        fake_get_connection,
    )

    result = await (
        database_metrics
        .get_database_metric_history(
            database,
            connection_id,
            hours=24,
            limit=2000,
        )
    )

    assert (
        result["connection_id"]
        == connection_id
    )

    assert (
        result["engine"]
        == "oracle"
    )

    assert result["count"] == 2

    assert (
        result[
            "sample_interval_seconds"
        ]
        ==
        database_metrics
        .settings
        .metrics_collector_interval_seconds
    )

    # API must return chronological
    # order for the chart.
    assert result["items"] == [
        older,
        newer,
    ]

    query = (
        database
        .history
        .last_filter
    )

    assert (
        query[
            "meta.connection_id"
        ]
        == connection_id
    )

    assert (
        query["meta.engine"]
        == "oracle"
    )

    assert (
        "$gte"
        in query["collected_at"]
    )

    assert (
        "$lte"
        in query["collected_at"]
    )

    assert (
        database
        .history
        .cursor
        .limit_value
        == 2000
    )

    assert (
        database
        .history
        .cursor
        .sort_args
        == (
            "collected_at",
            -1,
        )
    )

    assert (
        database
        .history
        .last_projection
        == {
            "_id": 0,
            "meta": 0,
        }
    )

    assert (
        query["collected_at"]["$gte"]
        < query["collected_at"]["$lte"]
    )


@pytest.mark.asyncio
async def test_history_can_return_empty_window(
    monkeypatch,
):
    database = FakeDatabase([])

    async def fake_get_connection(
        _database,
        _requested_id,
    ):
        return {
            "engine": "mysql",
        }

    monkeypatch.setattr(
        database_metrics,
        "get_database_connection",
        fake_get_connection,
    )

    result = await (
        database_metrics
        .get_database_metric_history(
            database,
            "connection-empty",
            hours=1,
            limit=50,
        )
    )

    assert result["count"] == 0
    assert result["items"] == []
    assert result["engine"] == "mysql"
    assert (
        database
        .history
        .cursor
        .limit_value
        == 50
    )


@pytest.mark.asyncio
async def test_oracle_history_returns_sql_text_cache_for_sampled_sql(monkeypatch):
    collected_at = datetime(2026, 8, 30, 6, 0, tzinfo=timezone.utc)
    sample = {
        "collected_at": collected_at,
        "status": "online",
        "active": 1,
        "oracle": {
            "top_sql": [
                {"sql_id": "abc123", "child_number": 0, "delta_cpu_time_us": 2000}
            ]
        },
    }
    database = FakeDatabase(
        [sample],
        sql_texts=[
            {
                "sql_id": "abc123",
                "child_number": 0,
                "sql_text": "select 1 from dual",
                "last_seen_at": collected_at,
            }
        ],
    )

    async def fake_get_connection(_database, _requested_id):
        return {"engine": "oracle"}

    monkeypatch.setattr(
        database_metrics,
        "get_database_connection",
        fake_get_connection,
    )

    result = await database_metrics.get_database_metric_history(
        database,
        "connection-1",
        hours=1,
        limit=100,
    )

    assert result["oracle_sql_texts"][0]["sql_id"] == "abc123"
    assert result["oracle_sql_texts"][0]["sql_text"] == "select 1 from dual"
    assert database.sql_texts.last_filter == {
        "connection_id": "connection-1",
        "sql_id": {"$in": ["abc123"]},
    }
