from datetime import datetime, timezone

from app.core.collections import COLLECTOR_STATUS_COLLECTION_NAME
from app.core.config import settings
from app.services.system_settings import runtime_monitoring_settings


async def get_collector_status(database) -> dict:
    monitoring = await runtime_monitoring_settings(database)
    interval = int(monitoring.get("database_interval_seconds", settings.metrics_collector_interval_seconds))
    server_interval = int(monitoring.get("server_interval_seconds", settings.server_metrics_interval_seconds))
    stale_seconds = int(monitoring.get("stale_threshold_seconds", settings.alert_collector_stale_seconds))
    document = await database[COLLECTOR_STATUS_COLLECTION_NAME].find_one(
        {"_id": "primary"},
        {"_id": 0, "owner_id": 0, "lease_until": 0},
    )
    if not document:
        return {
            "state": "not_started",
            "alive": False,
            "interval_seconds": interval,
            "server_interval_seconds": server_interval,
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
        ).total_seconds() <= stale_seconds and document.get("state") in {
            "starting",
            "running",
            "degraded",
        }

    return {
        **document,
        "alive": alive,
        "interval_seconds": document.get(
            "interval_seconds",
            interval,
        ),
        "server_interval_seconds": document.get(
            "server_interval_seconds",
            server_interval,
        ),
        "retention_hours": 24,
    }
