from fastapi import APIRouter, Depends, Query, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.alert import AlertClearResponse, AlertResponse, AlertSummaryResponse
from app.schemas.user import UserResponse
from app.services.alerting import clear_alert, clear_resolved_alerts, get_alert_summary, list_alerts


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=list[AlertResponse])
async def get_alerts(
    request: Request,
    status: str = Query(default="active", pattern="^(active|resolved|all)$"),
    severity: str | None = Query(default=None, pattern="^(warning|critical)$"),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await list_alerts(
        request.app.state.database,
        status=status,
        severity=severity,
        limit=limit,
    )


@router.get("/summary", response_model=AlertSummaryResponse)
async def alert_summary(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await get_alert_summary(request.app.state.database)


@router.delete("/resolved")
async def clear_all_resolved(
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    deleted = await clear_resolved_alerts(request.app.state.database)
    return {"cleared": deleted}


@router.delete("/{alert_id}", response_model=AlertClearResponse)
async def dismiss_alert(
    alert_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.MONITOR_READ)),
):
    return await clear_alert(
        request.app.state.database,
        alert_id,
        current_user.username,
    )
