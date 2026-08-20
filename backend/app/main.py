import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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

    frontend_dist = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "dist"
    )

    if frontend_dist.is_dir():
        frontend_dist = frontend_dist.resolve()
        index_file = frontend_dist / "index.html"
        api_prefix = settings.api_v1_prefix.strip("/")

        @application.get(
            "/{full_path:path}",
            include_in_schema=False,
        )
        async def serve_frontend(full_path: str):
            normalized_path = full_path.strip("/")

            if (
                normalized_path == api_prefix
                or normalized_path.startswith(
                    f"{api_prefix}/"
                )
            ):
                raise HTTPException(status_code=404)

            requested_file = (
                frontend_dist / normalized_path
            ).resolve()

            if (
                requested_file == frontend_dist
                or frontend_dist
                not in requested_file.parents
            ):
                requested_file = index_file

            if requested_file.is_file():
                return FileResponse(requested_file)

            return FileResponse(index_file)

        logger.info(
            "Serving production frontend from %s",
            frontend_dist,
        )
    else:
        logger.info(
            "Frontend build directory not found at %s; "
            "API-only mode enabled",
            frontend_dist,
        )

    return application


app = create_app()
