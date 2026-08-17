from datetime import datetime, timezone

import pytest

from app.core.collections import (
    METRICS_COLLECTION_NAME,
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
    ):
        self.history = (
            FakeHistoryCollection(
                items
            )
        )

    def __getitem__(
        self,
        name,
    ):
        assert (
            name
            == METRICS_COLLECTION_NAME
        )

        return self.history


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