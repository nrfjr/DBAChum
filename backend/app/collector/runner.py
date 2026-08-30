import asyncio
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone

from pymongo import AsyncMongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.collections import (
    COLLECTOR_STATUS_COLLECTION_NAME,
    ensure_telemetry_collections,
    telemetry_retention_seconds,
)
from app.core.config import settings
from app.core.indexes import create_indexes
from app.services.metrics_collector import (
    CollectorDeltaState,
    collect_collector_cycle,
)


logger = logging.getLogger(__name__)

COLLECTOR_STATUS_ID = "primary"
LEASE_SECONDS = 45
HEARTBEAT_SECONDS = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CollectorAlreadyRunning(RuntimeError):
    pass


class CollectorRuntime:
    def __init__(self, database):
        self.database = database
        self.collection = database[COLLECTOR_STATUS_COLLECTION_NAME]
        self.owner_id = str(uuid.uuid4())
        self.state = CollectorDeltaState()
        self.started_at = _utcnow()
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self._heartbeat_task: asyncio.Task | None = None

    async def acquire_lease(self) -> None:
        now = _utcnow()
        lease_until = now + timedelta(seconds=LEASE_SECONDS)
        try:
            document = await self.collection.find_one_and_update(
                {
                    "_id": COLLECTOR_STATUS_ID,
                    "$or": [
                        {"lease_until": {"$lt": now}},
                        {"lease_until": {"$exists": False}},
                        {"owner_id": self.owner_id},
                    ],
                },
                {
                    "$set": {
                        "owner_id": self.owner_id,
                        "state": "starting",
                        "hostname": self.hostname,
                        "pid": self.pid,
                        "started_at": self.started_at,
                        "last_heartbeat_at": now,
                        "lease_until": lease_until,
                        "interval_seconds": settings.metrics_collector_interval_seconds,
                        "server_interval_seconds": settings.server_metrics_interval_seconds,
                        "retention_hours": settings.metrics_retention_hours,
                        "retention_seconds": telemetry_retention_seconds(),
                        "last_error": None,
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as exc:
            document = None
            raise CollectorAlreadyRunning(
                "Another DBAChum collector currently owns the MongoDB lease."
            ) from exc

        if not document or document.get("owner_id") != self.owner_id:
            raise CollectorAlreadyRunning(
                "Another DBAChum collector currently owns the MongoDB lease."
            )

    async def _renew_lease(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            now = _utcnow()
            result = await self.collection.update_one(
                {
                    "_id": COLLECTOR_STATUS_ID,
                    "owner_id": self.owner_id,
                },
                {
                    "$set": {
                        "last_heartbeat_at": now,
                        "lease_until": now + timedelta(seconds=LEASE_SECONDS),
                    }
                },
            )
            if result.matched_count == 0:
                raise CollectorAlreadyRunning(
                    "DBAChum collector lost its MongoDB lease."
                )

    async def start_heartbeat(self) -> None:
        self._heartbeat_task = asyncio.create_task(
            self._renew_lease(),
            name="dbachum-collector-heartbeat",
        )

    async def stop_heartbeat(self) -> None:
        if self._heartbeat_task is None:
            return
        self._heartbeat_task.cancel()
        try:
            await self._heartbeat_task
        except asyncio.CancelledError:
            pass
        self._heartbeat_task = None

    async def mark_running(self) -> None:
        now = _utcnow()
        await self.collection.update_one(
            {"_id": COLLECTOR_STATUS_ID, "owner_id": self.owner_id},
            {
                "$set": {
                    "state": "running",
                    "last_heartbeat_at": now,
                    "lease_until": now + timedelta(seconds=LEASE_SECONDS),
                }
            },
        )

    async def mark_cycle_started(self, cycle_started_at: datetime) -> None:
        await self.collection.update_one(
            {"_id": COLLECTOR_STATUS_ID, "owner_id": self.owner_id},
            {
                "$set": {
                    "state": "running",
                    "last_cycle_started_at": cycle_started_at,
                    "last_error": None,
                }
            },
        )

    async def mark_cycle_completed(
        self,
        *,
        cycle_started_at: datetime,
        duration_ms: float,
        cycle,
    ) -> None:
        completed_at = _utcnow()
        next_cycle_at = cycle_started_at + timedelta(
            seconds=settings.metrics_collector_interval_seconds
        )
        status_update = {
            "state": "running",
            "last_cycle_completed_at": completed_at,
            "last_cycle_duration_ms": round(duration_ms, 1),
            "next_cycle_at": next_cycle_at,
            "database_targets_polled": cycle.database.target_count,
            "database_online": cycle.database.online_count,
            "database_failed": cycle.database.failed_count,
            "database_samples_inserted": cycle.database.inserted_count,
            "samples_inserted": cycle.inserted_count,
            "last_error": None,
        }
        if cycle.server.performed:
            status_update.update(
                {
                    "server_last_polled_at": completed_at,
                    "server_targets_polled": cycle.server.target_count,
                    "server_online": cycle.server.online_count,
                    "server_failed": cycle.server.failed_count,
                    "server_samples_inserted": cycle.server.inserted_count,
                }
            )

        await self.collection.update_one(
            {"_id": COLLECTOR_STATUS_ID, "owner_id": self.owner_id},
            {"$set": status_update},
        )

    async def mark_cycle_failed(
        self,
        cycle_started_at: datetime,
        exc: Exception,
    ) -> None:
        await self.collection.update_one(
            {"_id": COLLECTOR_STATUS_ID, "owner_id": self.owner_id},
            {
                "$set": {
                    "state": "degraded",
                    "last_cycle_completed_at": _utcnow(),
                    "next_cycle_at": cycle_started_at + timedelta(
                        seconds=settings.metrics_collector_interval_seconds
                    ),
                    "last_error": str(exc).strip() or exc.__class__.__name__,
                }
            },
        )

    async def release(self, state: str = "stopped") -> None:
        now = _utcnow()
        await self.collection.update_one(
            {"_id": COLLECTOR_STATUS_ID, "owner_id": self.owner_id},
            {
                "$set": {
                    "state": state,
                    "stopped_at": now,
                    "last_heartbeat_at": now,
                    "lease_until": now,
                },
                "$unset": {"owner_id": ""},
            },
        )

    async def run(self) -> None:
        await self.acquire_lease()
        await self.start_heartbeat()
        await self.mark_running()

        interval = settings.metrics_collector_interval_seconds
        next_cycle_monotonic = time.monotonic()
        logger.info(
            "DBAChum collector started owner_id=%s interval_seconds=%s retention_hours=24",
            self.owner_id,
            interval,
        )

        try:
            while True:
                if self._heartbeat_task is not None and self._heartbeat_task.done():
                    # Propagate lease/heartbeat failure instead of continuing to
                    # collect after another collector has taken ownership.
                    await self._heartbeat_task

                cycle_started_at = _utcnow()
                cycle_started_monotonic = time.monotonic()
                await self.mark_cycle_started(cycle_started_at)
                try:
                    cycle = await collect_collector_cycle(
                        self.database,
                        self.state,
                    )
                    duration_ms = (
                        time.monotonic() - cycle_started_monotonic
                    ) * 1000
                    await self.mark_cycle_completed(
                        cycle_started_at=cycle_started_at,
                        duration_ms=duration_ms,
                        cycle=cycle,
                    )
                    log_cycle = (
                        logger.warning
                        if cycle.database.failed_count or cycle.server.failed_count
                        else logger.debug
                    )
                    log_cycle(
                        "Collector cycle completed database=%s/%s server=%s/%s samples=%s duration_ms=%.1f",
                        cycle.database.online_count,
                        cycle.database.target_count,
                        cycle.server.online_count,
                        cycle.server.target_count,
                        cycle.inserted_count,
                        duration_ms,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("Collector cycle failed")
                    await self.mark_cycle_failed(cycle_started_at, exc)

                next_cycle_monotonic += interval
                sleep_seconds = max(0.0, next_cycle_monotonic - time.monotonic())
                if sleep_seconds == 0:
                    # If a cycle takes longer than the interval, start one fresh
                    # interval from now instead of creating a catch-up storm.
                    next_cycle_monotonic = time.monotonic()
                await asyncio.sleep(sleep_seconds)
        finally:
            await self.stop_heartbeat()
            await self.release()
            logger.info("DBAChum collector stopped owner_id=%s", self.owner_id)


async def run_collector_process() -> None:
    if not settings.metrics_collector_enabled:
        logger.warning("DBAChum collector is disabled by configuration.")
        return

    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
    )
    database = client[settings.mongodb_database]

    try:
        await database.command("ping")
        await create_indexes(database)
        await ensure_telemetry_collections(database)
        runtime = CollectorRuntime(database)
        await runtime.run()
    finally:
        await client.close()
