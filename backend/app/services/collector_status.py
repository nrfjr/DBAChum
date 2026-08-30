from datetime import datetime, timezone

from app.core.collections import COLLECTOR_STATUS_COLLECTION_NAME
from app.core.config import settings


async def get_collector_status(database) -> dict:
    document = await database[COLLECTOR_STATUS_COLLECTION_NAME].find_one(
        {"_id": "primary"},
        {"_id": 0, "owner_id": 0, "lease_until": 0},
    )
    if not document:
        return {
            "state": "not_started",
            "alive": False,
            "interval_seconds": settings.metrics_collector_interval_seconds,
            "server_interval_seconds": settings.server_metrics_interval_seconds,
            "retention_hours": 24,
        }

    heartbeat = document.get("last_heartbeat_at")
    alive = False
    if heartbeat is not None:
        now = datetime.now(timezone.utc)
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        alive = (
            now - heartbeat
        ).total_seconds() <= 30 and document.get("state") in {
            "starting",
            "running",
            "degraded",
        }

    return {
        **document,
        "alive": alive,
        "interval_seconds": document.get(
            "interval_seconds",
            settings.metrics_collector_interval_seconds,
        ),
        "server_interval_seconds": document.get(
            "server_interval_seconds",
            settings.server_metrics_interval_seconds,
        ),
        "retention_hours": 24,
    }
