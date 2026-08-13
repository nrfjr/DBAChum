import logging
from typing import Literal


logger = logging.getLogger(__name__)


HealthStatus = Literal[
    "healthy",
    "unhealthy",
]


async def check_mongodb(
    database,
) -> HealthStatus:
    try:
        await database.command("ping")
        return "healthy"

    except Exception:
        logger.warning(
            "MongoDB health check failed",
            exc_info=True,
        )

        return "unhealthy"