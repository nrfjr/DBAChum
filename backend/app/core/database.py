import logging

from fastapi import FastAPI
from pymongo import AsyncMongoClient

from app.core.config import settings


logger = logging.getLogger(__name__)


async def connect_to_mongodb(app: FastAPI) -> None:
    client = AsyncMongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
    )

    database = client[settings.mongodb_database]

    app.state.mongodb_client = client
    app.state.database = database

    try:
        await database.command("ping")

        logger.info(
            "MongoDB connection established database=%s",
            settings.mongodb_database,
        )

    except Exception:
        logger.exception(
            "MongoDB connection failed database=%s",
            settings.mongodb_database,
        )


async def close_mongodb(app: FastAPI) -> None:
    client = getattr(
        app.state,
        "mongodb_client",
        None,
    )

    if client is not None:
        await client.close()
        logger.info("MongoDB connection closed")