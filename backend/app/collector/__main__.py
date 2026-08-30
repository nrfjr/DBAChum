import asyncio
import logging

from app.collector.runner import (
    CollectorAlreadyRunning,
    run_collector_process,
)
from app.core.config import settings
from app.core.logging import configure_logging


configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


def main() -> None:
    try:
        asyncio.run(run_collector_process())
    except CollectorAlreadyRunning as exc:
        logger.error(str(exc))
        raise SystemExit(2) from exc
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
