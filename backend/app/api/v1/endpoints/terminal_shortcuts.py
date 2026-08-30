from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.terminal_shortcut import (
    TerminalSessionAuditResponse,
    TerminalShortcutCreate,
    TerminalShortcutResponse,
    TerminalShortcutUpdate,
)
from app.schemas.user import UserResponse
from app.services.server_terminal import list_terminal_audit
from app.services.terminal_shortcuts import (
    create_terminal_shortcut,
    delete_terminal_shortcut,
    list_terminal_shortcuts,
    list_terminal_shortcuts_for_server,
    update_terminal_shortcut,
)


router = APIRouter(prefix="/terminal", tags=["SSH Terminal"])


@router.get("/shortcuts", response_model=list[TerminalShortcutResponse])
async def get_shortcuts(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    return await list_terminal_shortcuts(request.app.state.database)


@router.get("/shortcuts/server/{server_id}", response_model=list[TerminalShortcutResponse])
async def get_server_shortcuts(
    server_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await list_terminal_shortcuts_for_server(request.app.state.database, server_id)


@router.post("/shortcuts", response_model=TerminalShortcutResponse, status_code=status.HTTP_201_CREATED)
async def create_shortcut(
    data: TerminalShortcutCreate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    return await create_terminal_shortcut(request.app.state.database, data)


@router.put("/shortcuts/{shortcut_id}", response_model=TerminalShortcutResponse)
async def update_shortcut(
    shortcut_id: str,
    data: TerminalShortcutUpdate,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    return await update_terminal_shortcut(request.app.state.database, shortcut_id, data)


@router.delete("/shortcuts/{shortcut_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shortcut(
    shortcut_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    await delete_terminal_shortcut(request.app.state.database, shortcut_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit", response_model=list[TerminalSessionAuditResponse])
async def get_terminal_audit(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserResponse = Depends(require_permission(Permission.SERVER_MANAGE)),
):
    return await list_terminal_audit(request.app.state.database, limit=limit)
