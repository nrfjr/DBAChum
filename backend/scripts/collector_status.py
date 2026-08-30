import asyncio
from datetime import datetime, timezone

from pymongo import AsyncMongoClient

from app.core.collections import COLLECTOR_STATUS_COLLECTION_NAME
from app.core.config import settings


def _fmt(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


async def main() -> None:
    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
    )
    database = client[settings.mongodb_database]
    try:
        await database.command("ping")
        document = await database[COLLECTOR_STATUS_COLLECTION_NAME].find_one(
            {"_id": "primary"},
            {"owner_id": 0},
        )
        if not document:
            print("DBAChum collector has not started yet.")
            return

        heartbeat = document.get("last_heartbeat_at")
        alive = False
        if heartbeat:
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)
            alive = (
                datetime.now(timezone.utc) - heartbeat
            ).total_seconds() <= 30

        print(f"State: {document.get('state', 'unknown')}")
        print(f"Alive: {'yes' if alive else 'no'}")
        print(f"Host/PID: {document.get('hostname', '-')} / {document.get('pid', '-')}")
        print(f"Heartbeat: {_fmt(document.get('last_heartbeat_at'))}")
        print(f"Last cycle: {_fmt(document.get('last_cycle_completed_at'))}")
        print(f"Next cycle: {_fmt(document.get('next_cycle_at'))}")
        print(
            "Databases: "
            f"{document.get('database_online', 0)}/"
            f"{document.get('database_targets_polled', 0)} online"
        )
        print(
            "Servers: "
            f"{document.get('server_online', 0)}/"
            f"{document.get('server_targets_polled', 0)} online (polled this cycle)"
        )
        print(f"Samples inserted: {document.get('samples_inserted', 0)}")
        print(f"Retention: {document.get('retention_hours', 24)} hours")
        if document.get("last_error"):
            print(f"Last error: {document['last_error']}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
