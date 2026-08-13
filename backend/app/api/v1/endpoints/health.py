from fastapi import (
    APIRouter,
    Request,
    Response,
    status,
)

from app.core.config import settings
from app.schemas.health import (
    HealthResponse,
    ReadinessResponse,
)
from app.services.health import check_mongodb


router = APIRouter(
    prefix="/health",
    tags=["System"],
)


@router.get(
    "",
    response_model=HealthResponse,
)
async def health(
    request: Request,
) -> HealthResponse:
    mongodb_status = await check_mongodb(
        request.app.state.database
    )

    return HealthResponse(
        mongodb=mongodb_status,
        environment=settings.environment,
        version=settings.app_version,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
)
async def readiness(
    request: Request,
    response: Response,
) -> ReadinessResponse:
    mongodb_status = await check_mongodb(
        request.app.state.database
    )

    ready = mongodb_status == "healthy"

    if not ready:
        response.status_code = (
            status.HTTP_503_SERVICE_UNAVAILABLE
        )

    return ReadinessResponse(
        ready=ready,
        mongodb=mongodb_status,
    )