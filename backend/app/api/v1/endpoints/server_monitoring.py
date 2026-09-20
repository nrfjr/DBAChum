import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.server_monitoring import (
    ServerHealthSnapshot,
    SshConnectionTestResponse,
    SshTrustHostKeyRequest,
)
from app.schemas.user import UserResponse
from app.services.server_monitoring import (
    collect_server_health,
    test_server_ssh,
    trust_server_ssh_host_key,
)


LIVE_HEALTH_INTERVAL_SECONDS = 5.0


router = APIRouter(
    prefix="/servers",
    tags=["Server Monitoring"],
)


@router.post("/{server_id}/ssh/test", response_model=SshConnectionTestResponse)
async def test_ssh_connection(
    server_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.CONNECTION_TEST)),
):
    return await test_server_ssh(request.app.state.database, server_id)


@router.post("/{server_id}/ssh/trust", response_model=SshConnectionTestResponse)
async def trust_ssh_host_key(
    server_id: str,
    data: SshTrustHostKeyRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    return await trust_server_ssh_host_key(
        request.app.state.database,
        server_id,
        data.fingerprint,
    )


@router.get("/{server_id}/health", response_model=ServerHealthSnapshot)
async def get_server_health(
    server_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await collect_server_health(request.app.state.database, server_id)


@router.get("/{server_id}/health/live")
async def stream_server_health(
    server_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    database = request.app.state.database
    first_snapshot = await collect_server_health(database, server_id)

    async def events():
        yield "retry: 5000\n\n"
        yield f"event: health\ndata: {first_snapshot.model_dump_json()}\n\n"

        while True:
            await asyncio.sleep(LIVE_HEALTH_INTERVAL_SECONDS)
            if await request.is_disconnected():
                return

            try:
                snapshot = await collect_server_health(database, server_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                message = getattr(exc, "message", None) or str(exc) or "Unable to collect live server metrics."
                payload = json.dumps({"message": message})
                yield f"event: metrics-error\ndata: {payload}\n\n"
                continue

            yield f"event: health\ndata: {snapshot.model_dump_json()}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
