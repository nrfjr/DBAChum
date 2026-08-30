from datetime import datetime, timedelta, timezone

from app.core.collections import METRICS_COLLECTION_NAME
from app.core.config import settings
from app.services.database_connections import get_database_connection


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

    # Mongo returned newest → oldest
    # because we want the newest N points.
    #
    # Charts want chronological order,
    # so reverse them before returning.
    items.reverse()

    return {
        "connection_id": connection_id,
        "engine": connection["engine"],
        "from_at": from_at,
        "to_at": to_at,
        "sample_interval_seconds": settings.metrics_collector_interval_seconds,
        "count": len(items),
        "items": items,
    }
