from datetime import datetime, timezone
from typing import Any

from bson import ObjectId

from app.core.exceptions import AppError
from app.schemas.database_action import (
    DatabaseActionAuditResponse,
    DatabaseActionRisk,
    DatabaseActionStatus,
)
from app.schemas.user import UserResponse


AUDIT_LIST_LIMIT = 100


def _parse_audit_id(audit_id: str) -> ObjectId:
    try:
        return ObjectId(audit_id)
    except Exception:
        raise AppError(
            "Database action audit record not found.",
            code="DATABASE_ACTION_AUDIT_NOT_FOUND",
            status_code=404,
        )


def database_action_to_response(
    document: dict,
) -> DatabaseActionAuditResponse:
    return DatabaseActionAuditResponse(
        id=str(document["_id"]),
        connection_id=document["connection_id"],
        engine=document["engine"],
        action=document["action"],
        target=document.get("target"),
        risk=document["risk"],
        status=document["status"],
        operator_user_id=document["operator_user_id"],
        operator_username=document["operator_username"],
        request_reference=document.get(
            "request_reference"
        ),
        before=document.get("before"),
        after=document.get("after"),
        details=document.get("details", {}),
        started_at=document["started_at"],
        completed_at=document.get("completed_at"),
        error=document.get("error"),
    )


async def start_database_action(
    database,
    *,
    connection_id: str,
    engine: str,
    action: str,
    operator: UserResponse,
    target: str | None = None,
    risk: DatabaseActionRisk = DatabaseActionRisk.SENSITIVE,
    request_reference: str | None = None,
    before: dict[str, Any] | None = None,
    details: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)

    document = {
        "connection_id": connection_id,
        "engine": engine,
        "action": action,
        "target": target,
        "risk": risk.value,
        "status": DatabaseActionStatus.RUNNING.value,
        "operator_user_id": operator.id,
        "operator_username": operator.username,
        "request_reference": request_reference,
        "before": before,
        "after": None,
        "details": details or {},
        "started_at": now,
        "completed_at": None,
        "error": None,
    }

    result = await (
        database.database_action_audit.insert_one(
            document
        )
    )

    return str(result.inserted_id)


async def finish_database_action(
    database,
    audit_id: str,
    *,
    status: DatabaseActionStatus,
    after: dict[str, Any] | None = None,
    error: str | None = None,
    details: dict[str, Any] | None = None,
) -> DatabaseActionAuditResponse:
    object_id = _parse_audit_id(audit_id)

    update: dict[str, Any] = {
        "status": status.value,
        "completed_at": datetime.now(timezone.utc),
        "after": after,
        "error": error,
    }

    if details is not None:
        update["details"] = details

    result = await database.database_action_audit.update_one(
        {
            "_id": object_id,
            "status": DatabaseActionStatus.RUNNING.value,
        },
        {
            "$set": update,
        },
    )

    if result.matched_count == 0:
        raise AppError(
            "Database action audit record not found or already completed.",
            code="DATABASE_ACTION_AUDIT_NOT_RUNNING",
            status_code=409,
        )

    document = await (
        database.database_action_audit.find_one(
            {"_id": object_id}
        )
    )

    return database_action_to_response(document)


async def list_database_actions(
    database,
    connection_id: str,
    *,
    limit: int = AUDIT_LIST_LIMIT,
) -> list[DatabaseActionAuditResponse]:
    safe_limit = max(
        1,
        min(limit, AUDIT_LIST_LIMIT),
    )

    cursor = (
        database.database_action_audit
        .find({"connection_id": connection_id})
        .sort("started_at", -1)
    )

    documents = await cursor.to_list(safe_limit)

    return [
        database_action_to_response(document)
        for document in documents
    ]
