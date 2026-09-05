from fastapi import APIRouter, Depends, Request

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
