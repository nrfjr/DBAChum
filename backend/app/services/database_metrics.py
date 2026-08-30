from datetime import datetime, timedelta, timezone

from app.core.collections import (
    METRICS_COLLECTION_NAME,
    ORACLE_SQL_TEXT_COLLECTION_NAME,
)
from app.core.config import settings
from app.services.database_connections import get_database_connection


MAX_SQL_TEXT_ROWS = 2000


def _oracle_sql_ids(items: list[dict]) -> list[str]:
    """Return the unique SQL IDs represented by the returned history window."""
    seen: set[str] = set()
    result: list[str] = []

    for sample in items:
        oracle = sample.get("oracle") or {}
        for item in oracle.get("top_sql") or []:
            sql_id = item.get("sql_id")
            if not sql_id:
                continue
            normalized = str(sql_id)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
            if len(result) >= MAX_SQL_TEXT_ROWS:
                return result

    return result


async def _load_oracle_sql_texts(
    database,
    connection_id: str,
    items: list[dict],
) -> list[dict]:
    sql_ids = _oracle_sql_ids(items)
    if not sql_ids:
        return []

    cursor = (
        database[ORACLE_SQL_TEXT_COLLECTION_NAME]
        .find(
            {
                "connection_id": connection_id,
                "sql_id": {"$in": sql_ids},
            },
            {
                "_id": 0,
                "connection_id": 0,
                "expires_at": 0,
                "first_seen_at": 0,
            },
        )
        .sort("last_seen_at", -1)
        .limit(MAX_SQL_TEXT_ROWS)
    )
    return await cursor.to_list(None)


async def get_database_metric_history(
    database,
    connection_id: str,
    hours: int,
    limit: int,
):
    connection = await get_database_connection(
        database,
        connection_id,
    )

    # History is intentionally bounded to DBAChum's rolling 24-hour
    # telemetry window even for internal callers that bypass API validation.
    hours = min(max(int(hours), 1), 24)

    to_at = datetime.now(timezone.utc)
    from_at = to_at - timedelta(hours=hours)

    collection = database[METRICS_COLLECTION_NAME]

    cursor = (
        collection.find(
            {
                "meta.connection_id": connection_id,
                "meta.engine": connection["engine"],
                "collected_at": {
                    "$gte": from_at,
                    "$lte": to_at,
                },
            },
            {
                "_id": 0,
                "meta": 0,
            },
        )
        .sort(
            "collected_at",
            -1,
        )
        .limit(limit)
    )

    items = await cursor.to_list(None)

    # Mongo returned newest → oldest because we want the newest N points.
    # Charts and range aggregation want chronological order.
    items.reverse()

    oracle_sql_texts: list[dict] = []
    if connection["engine"] == "oracle" and items:
        oracle_sql_texts = await _load_oracle_sql_texts(
            database,
            connection_id,
            items,
        )

    return {
        "connection_id": connection_id,
        "engine": connection["engine"],
        "from_at": from_at,
        "to_at": to_at,
        "sample_interval_seconds": settings.metrics_collector_interval_seconds,
        "count": len(items),
        "items": items,
        "oracle_sql_texts": oracle_sql_texts,
    }
