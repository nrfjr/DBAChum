from fastapi import APIRouter, WebSocket

from app.core.config import settings
from app.core.permissions import Permission, has_permission
from app.services.auth import get_user_from_session
from app.services.server_terminal import run_terminal_session


router = APIRouter(prefix="/terminal", tags=["SSH Terminal"])


@router.websocket("/ws/{server_id}")
async def server_terminal_websocket(
    websocket: WebSocket,
    server_id: str,
):
    await websocket.accept()
    database = websocket.app.state.database
    session_token = websocket.cookies.get(settings.session_cookie_name)

    if not session_token:
        await websocket.send_json(
            {"type": "error", "code": "AUTH_REQUIRED", "message": "Authentication required."}
        )
        await websocket.close(code=4401)
        return

    user = await get_user_from_session(database, session_token)
    if user is None or not user.get("is_active", True):
        await websocket.send_json(
            {"type": "error", "code": "INVALID_SESSION", "message": "Session is invalid or expired."}
        )
        await websocket.close(code=4401)
        return

    if not has_permission(user.get("role", "viewer"), Permission.DBA_OPERATE):
        await websocket.send_json(
            {"type": "error", "code": "FORBIDDEN", "message": "You do not have permission to open SSH terminals."}
        )
        await websocket.close(code=4403)
        return

    try:
        cols = int(websocket.query_params.get("cols", "100"))
        rows = int(websocket.query_params.get("rows", "30"))
    except ValueError:
        cols, rows = 100, 30

    await run_terminal_session(
        websocket,
        database,
        user=user,
        server_id=server_id,
        cols=cols,
        rows=rows,
    )

    try:
        await websocket.close()
    except Exception:
        pass
