import asyncio

from pymongo import AsyncMongoClient

from app.core.collections import (
    ensure_metrics_collection,
)
from app.core.config import settings
from app.services.metrics_collector import (
    collect_metrics_once,
)


async def main() -> None:
    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
    )

    database = client[
        settings.mongodb_database
    ]

    try:
        await database.command(
            "ping"
        )

        await ensure_metrics_collection(
            database
        )

        inserted_count = (
            await collect_metrics_once(
                database
            )
        )

        print(
            "Metric collection complete. "
            f"Inserted {inserted_count} "
            "sample(s)."
        )

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(
        main()
    )