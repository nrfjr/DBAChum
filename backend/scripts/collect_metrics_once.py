import asyncio

from pymongo import AsyncMongoClient

from app.core.collections import ensure_telemetry_collections
from app.core.config import settings
from app.core.indexes import create_indexes
from app.services.metrics_collector import (
    CollectorDeltaState,
    collect_collector_cycle,
)


async def main() -> None:
    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
    )
    database = client[settings.mongodb_database]

    try:
        await database.command("ping")
        await create_indexes(database)
        await ensure_telemetry_collections(database)

        cycle = await collect_collector_cycle(
            database,
            CollectorDeltaState(),
        )

        print(
            "Metric collection complete. "
            f"Database samples: {cycle.database.inserted_count}; "
            f"server samples: {cycle.server.inserted_count}."
        )
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
