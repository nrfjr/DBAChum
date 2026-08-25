from datetime import datetime, timezone

import pytest

from app.core.collections import (
    METRICS_COLLECTION_NAME,
)
from app.services import metrics_collector


class FakeCursor:
    def __init__(self, items):
        self.items = items

    def sort(self, *_args):
        return self

    async def to_list(
        self,
        _length,
    ):
        return list(self.items)


class FakeConnectionsCollection:
    def __init__(self, items):
        self.items = items
        self.last_query = None

    def find(self, query):
        self.last_query = query

        return FakeCursor(
            self.items
        )


class FakeInsertManyResult:
    def __init__(
        self,
        inserted_count,
    ):
        self.inserted_ids = list(
            range(inserted_count)
        )


class FakeMetricsCollection:
    def __init__(self):
        self.inserted = []

    async def insert_many(
        self,
        documents,
    ):
        self.inserted.extend(
            documents
        )

        return FakeInsertManyResult(
            len(documents)
        )


class FakeDatabase:
    def __init__(
        self,
        connections,
    ):
        self.database_connections = (
            FakeConnectionsCollection(
                connections
            )
        )

        self.metric_samples = (
            FakeMetricsCollection()
        )

    def __getitem__(
        self,
        name,
    ):
        assert (
            name
            == METRICS_COLLECTION_NAME
        )

        return self.metric_samples


def test_build_metric_sample_preserves_zero_and_null():
    checked_at = datetime.now(
        timezone.utc
    )

    sample = (
        metrics_collector
        .build_metric_sample(
            {
                "connection_id":
                    "connection-1",

                "engine":
                    "oracle",

                "checked_at":
                    checked_at,

                "status":
                    "online",

                "response_time_ms":
                    125.5,

                "active":
                    0,

                "connections":
                    None,

                "blocked":
                    0,

                "uptime_seconds":
                    3600,

                "warnings":
                    [],

                "error":
                    None,
            }
        )
    )

    assert sample["meta"] == {
        "connection_id":
            "connection-1",

        "engine":
            "oracle",
    }

    assert (
        sample["checked_at"]
        == checked_at
    )

    # Critical monitoring semantics.
    assert sample["active"] == 0
    assert (
        sample["connections"]
        is None
    )
    assert sample["blocked"] == 0

    # Historical timestamps stay UTC.
    assert (
        sample["collected_at"]
        .utcoffset()
        .total_seconds()
        == 0
    )


@pytest.mark.asyncio
async def test_collect_metrics_once():
    database = FakeDatabase(
        [
            {
                "_id": "one",
                "engine": "oracle",
            },
            {
                "_id": "two",
                "engine": "mysql",
            },
        ]
    )

    original_collect = (
        metrics_collector
        .collect_database_overview
    )

    async def fake_collect(
        connection,
    ):
        return {
            "connection_id":
                str(
                    connection["_id"]
                ),

            "engine":
                connection["engine"],

            "status":
                "online",

            "active":
                1,

            "connections":
                2,

            "blocked":
                0,

            "warnings":
                [],

            "error":
                None,
        }

    metrics_collector.collect_database_overview = (
        fake_collect
    )

    try:
        count = await (
            metrics_collector
            .collect_metrics_once(
                database
            )
        )

    finally:
        metrics_collector.collect_database_overview = (
            original_collect
        )

    assert (
        database
        .database_connections
        .last_query
        == metrics_collector.monitored_connections_filter()
    )

    assert count == 2

    assert (
        len(
            database
            .metric_samples
            .inserted
        )
        == 2
    )

    connection_ids = {
        sample["meta"][
            "connection_id"
        ]
        for sample
        in database
        .metric_samples
        .inserted
    }

    assert connection_ids == {
        "one",
        "two",
    }