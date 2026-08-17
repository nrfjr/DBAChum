import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import (
    close_mongodb,
    connect_to_mongodb,
)
from app.core.exceptions import (
    AppError,
    app_error_handler,
    unhandled_exception_handler,
)
from app.core.logging import configure_logging
from app.services.metrics_collector import (
    run_metrics_collector,
)

configure_logging(settings.log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    logger.info(
        "Starting %s version=%s environment=%s",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )

    await connect_to_mongodb(app)

    collector_task = None

    if settings.metrics_collector_enabled:
        collector_task = asyncio.create_task(
            run_metrics_collector(app.state.database),
            name="database-metrics-collector",
        )

        app.state.metrics_collector_task = collector_task

    try:
        yield

    finally:
        if collector_task is not None:
            collector_task.cancel()

            try:
                await collector_task

            except asyncio.CancelledError:
                pass

        await close_mongodb(app)

        logger.info("DBAChum API stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Backend API for the DBAChum " "database administration platform."
        ),
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.add_exception_handler(
        AppError,
        app_error_handler,
    )

    application.add_exception_handler(
        Exception,
        unhandled_exception_handler,
    )

    application.include_router(
        api_router,
        prefix=settings.api_v1_prefix,
    )

    return application


app = create_app()
