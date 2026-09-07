from fastapi import APIRouter, Depends, Request

from app.core.permissions import Permission
from app.dependencies.permissions import require_permission
from app.schemas.database_job import DatabaseJobsResponse, JobOperationRequest
from app.schemas.database_action import DatabaseActionAuditResponse
from app.schemas.user import UserResponse
from app.services.database_jobs import load_database_jobs, operate_database_job

router = APIRouter(prefix="/databases", tags=["Database Jobs"])


@router.get("/{connection_id}/jobs", response_model=DatabaseJobsResponse)
async def jobs(
    connection_id: str,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DATABASE_INSPECT)),
):
    return await load_database_jobs(request.app.state.database, connection_id)


@router.post("/{connection_id}/jobs/operation", response_model=DatabaseActionAuditResponse)
async def job_operation(
    connection_id: str,
    data: JobOperationRequest,
    request: Request,
    current_user: UserResponse = Depends(require_permission(Permission.DBA_OPERATE)),
):
    return await operate_database_job(request.app.state.database, connection_id, data, current_user)
