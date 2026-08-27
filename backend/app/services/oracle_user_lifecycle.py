from __future__ import annotations

from datetime import datetime, timezone

from app.connectors.oracle_user_lifecycle import (
    apply_oracle_user_access_changes,
    execute_oracle_user_account_action,
    get_oracle_user_lifecycle_state,
    reset_oracle_user_password,
)
from app.connectors.oracle_provisioning import (
    is_sensitive_reference_role,
    normalize_oracle_identifier,
)
from app.core.exceptions import AppError
from app.schemas.database_action import DatabaseActionRisk, DatabaseActionStatus
from app.schemas.oracle_dba import (
    OracleUserAccountActionRequest,
    OracleUserEditExecuteRequest,
    OracleUserEditPreviewResponse,
    OracleUserEditRequest,
    OracleUserEditResponse,
    OracleUserLifecycleActionResponse,
    OracleUserPasswordResetRequest,
)
from app.schemas.user import UserResponse
from app.services.database_actions import finish_database_action, start_database_action
from app.services.oracle_dba import get_oracle_target


def _state_for_audit(state: dict) -> dict:
    return {
        "username": state["username"],
        "status": state["status"],
        "locked": state["locked"],
        "expired": state["expired"],
        "default_tablespace": state.get("default_tablespace"),
        "temporary_tablespace": state.get("temporary_tablespace"),
        "profile": state.get("profile"),
        "roles": sorted(str(role["name"]) for role in state.get("roles", [])),
        "system_privileges": sorted(
            str(privilege["name"]) for privilege in state.get("system_privileges", [])
        ),
    }


def _resolve_edit_request(state: dict, data: OracleUserEditRequest) -> dict:
    current_roles = {str(role["name"]).upper() for role in state.get("roles", [])}
    desired_roles = {
        normalize_oracle_identifier(role, field_name="Role") for role in data.roles
    }

    available_role_sensitivity = {
        str(role["name"]).upper(): bool(role.get("sensitive"))
        for role in state.get("available_roles", [])
    }
    blocked_additions = sorted(
        role
        for role in desired_roles - current_roles
        if is_sensitive_reference_role(role) or available_role_sensitivity.get(role, False)
    )
    if blocked_additions:
        raise AppError(
            "Sensitive roles cannot be added through this workflow: "
            + ", ".join(blocked_additions),
            code="ORACLE_SENSITIVE_ROLE_ADD_BLOCKED",
            status_code=403,
        )

    default_tablespace = normalize_oracle_identifier(
        data.default_tablespace or state.get("default_tablespace") or "",
        field_name="Default tablespace",
    )
    temporary_tablespace = normalize_oracle_identifier(
        data.temporary_tablespace or state.get("temporary_tablespace") or "",
        field_name="Temporary tablespace",
    )
    profile = normalize_oracle_identifier(
        data.profile or state.get("profile") or "",
        field_name="Profile",
    )

    return {
        "roles": desired_roles,
        "default_tablespace": default_tablespace,
        "temporary_tablespace": temporary_tablespace,
        "profile": profile,
        "locked": bool(state.get("locked")) if data.locked is None else bool(data.locked),
    }


def _build_changes(state: dict, resolved: dict) -> list[dict]:
    changes: list[dict] = []

    scalar_fields = (
        ("default_tablespace", "Default tablespace"),
        ("temporary_tablespace", "Temporary tablespace"),
        ("profile", "Profile"),
    )
    for key, label in scalar_fields:
        before = str(state.get(key) or "").upper()
        after = str(resolved[key] or "").upper()
        if before != after:
            changes.append(
                {
                    "component": "account",
                    "action": "alter",
                    "label": label,
                    "before": before or None,
                    "after": after or None,
                    "sensitive": False,
                }
            )

    if bool(state.get("locked")) != bool(resolved["locked"]):
        changes.append(
            {
                "component": "account",
                "action": "lock" if resolved["locked"] else "unlock",
                "label": "Account state",
                "before": "LOCKED" if state.get("locked") else "UNLOCKED",
                "after": "LOCKED" if resolved["locked"] else "UNLOCKED",
                "sensitive": False,
            }
        )

    current_roles = {str(role["name"]).upper() for role in state.get("roles", [])}
    desired_roles = set(resolved["roles"])
    for role in sorted(desired_roles - current_roles):
        changes.append(
            {
                "component": "role",
                "action": "grant",
                "label": role,
                "before": None,
                "after": "GRANTED",
                "sensitive": is_sensitive_reference_role(role),
            }
        )
    for role in sorted(current_roles - desired_roles):
        changes.append(
            {
                "component": "role",
                "action": "revoke",
                "label": role,
                "before": "GRANTED",
                "after": None,
                "sensitive": is_sensitive_reference_role(role),
            }
        )

    return changes


async def load_oracle_user_lifecycle_state(database, connection_id: str, username: str):
    connection = await get_oracle_target(database, connection_id)
    return await get_oracle_user_lifecycle_state(connection, username)


async def build_oracle_user_edit_preview(
    database,
    connection_id: str,
    username: str,
    data: OracleUserEditRequest,
):
    connection = await get_oracle_target(database, connection_id)
    state = await get_oracle_user_lifecycle_state(connection, username)
    resolved = _resolve_edit_request(state, data)
    changes = _build_changes(state, resolved)

    warnings = list(state.get("warnings", []))
    if any(change["sensitive"] and change["action"] == "revoke" for change in changes):
        warnings.append(
            "At least one sensitive role will be revoked. Review the impact before applying."
        )
    if not changes:
        warnings.append("No Oracle account or role changes are pending.")

    return OracleUserEditPreviewResponse(
        username=state["username"],
        generated_at=datetime.now(timezone.utc),
        ready_to_execute=bool(changes),
        changes=changes,
        warnings=warnings,
    )


async def execute_oracle_user_edit(
    database,
    connection_id: str,
    username: str,
    data: OracleUserEditExecuteRequest,
    operator: UserResponse,
):
    connection = await get_oracle_target(database, connection_id)
    before = await get_oracle_user_lifecycle_state(connection, username)
    resolved = _resolve_edit_request(before, data)
    changes = _build_changes(before, resolved)
    if not changes:
        raise AppError(
            "No Oracle account or role changes are pending.",
            code="ORACLE_USER_EDIT_NO_CHANGES",
            status_code=409,
        )

    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine="oracle",
        action="edit_user_access",
        target=before["username"],
        operator=operator,
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=data.request_reference,
        before=_state_for_audit(before),
        details={"planned_changes": changes},
    )

    try:
        await apply_oracle_user_access_changes(
            connection,
            username=before["username"],
            default_tablespace=resolved["default_tablespace"],
            temporary_tablespace=resolved["temporary_tablespace"],
            profile=resolved["profile"],
            roles=sorted(resolved["roles"]),
            locked=resolved["locked"],
        )
        after = await get_oracle_user_lifecycle_state(connection, before["username"])
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.SUCCEEDED,
            after=_state_for_audit(after),
            details={"changes_applied": changes},
        )
        return OracleUserEditResponse(
            audit_id=audit_id,
            status="succeeded",
            username=before["username"],
            changes_applied=len(changes),
            after=after,
        )
    except Exception as exc:
        try:
            after = await get_oracle_user_lifecycle_state(connection, before["username"])
        except Exception:
            after = before
        changed = _state_for_audit(after) != _state_for_audit(before)
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.PARTIAL if changed else DatabaseActionStatus.FAILED,
            after=_state_for_audit(after),
            error=str(exc),
            details={"planned_changes": changes},
        )
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "Oracle user access update failed.",
            code="ORACLE_USER_EDIT_FAILED",
            status_code=400,
        ) from exc


async def execute_oracle_user_password_reset(
    database,
    connection_id: str,
    username: str,
    data: OracleUserPasswordResetRequest,
    operator: UserResponse,
):
    connection = await get_oracle_target(database, connection_id)
    before = await get_oracle_user_lifecycle_state(connection, username)
    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine="oracle",
        action="reset_user_password",
        target=before["username"],
        operator=operator,
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=data.request_reference,
        before=_state_for_audit(before),
        details={
            "password_changed": True,
            "password_persisted": False,
            "expire_after_reset": data.expire_after_reset,
        },
    )

    try:
        await reset_oracle_user_password(
            connection,
            username=before["username"],
            password=data.password,
            expire_after_reset=data.expire_after_reset,
        )
        after = await get_oracle_user_lifecycle_state(connection, before["username"])
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.SUCCEEDED,
            after=_state_for_audit(after),
            details={
                "password_changed": True,
                "password_persisted": False,
                "expire_after_reset": data.expire_after_reset,
            },
        )
        return OracleUserLifecycleActionResponse(
            audit_id=audit_id,
            status="succeeded",
            username=before["username"],
            action="reset_password",
            after=after,
        )
    except Exception as exc:
        try:
            after = await get_oracle_user_lifecycle_state(connection, before["username"])
        except Exception:
            after = before
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            after=_state_for_audit(after),
            error=str(exc),
            details={
                "password_changed": False,
                "password_persisted": False,
                "expire_after_reset": data.expire_after_reset,
            },
        )
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "Oracle password reset failed.",
            code="ORACLE_PASSWORD_RESET_FAILED",
            status_code=400,
        ) from exc


async def execute_oracle_user_lifecycle_action(
    database,
    connection_id: str,
    username: str,
    data: OracleUserAccountActionRequest,
    operator: UserResponse,
):
    if data.action not in {"lock", "unlock", "expire_password"}:
        raise AppError(
            "Unsupported Oracle account action.",
            code="ORACLE_ACCOUNT_ACTION_INVALID",
            status_code=400,
        )

    connection = await get_oracle_target(database, connection_id)
    before = await get_oracle_user_lifecycle_state(connection, username)
    if data.action == "lock" and before["locked"]:
        raise AppError("Account is already locked.", code="ORACLE_ACCOUNT_ALREADY_LOCKED", status_code=409)
    if data.action == "unlock" and not before["locked"]:
        raise AppError("Account is already unlocked.", code="ORACLE_ACCOUNT_ALREADY_UNLOCKED", status_code=409)
    if data.action == "expire_password" and before["expired"]:
        raise AppError("Password is already expired.", code="ORACLE_PASSWORD_ALREADY_EXPIRED", status_code=409)

    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine="oracle",
        action=f"user_{data.action}",
        target=before["username"],
        operator=operator,
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=data.request_reference,
        before=_state_for_audit(before),
    )

    try:
        await execute_oracle_user_account_action(
            connection,
            username=before["username"],
            action=data.action,
        )
        after = await get_oracle_user_lifecycle_state(connection, before["username"])
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.SUCCEEDED,
            after=_state_for_audit(after),
        )
        return OracleUserLifecycleActionResponse(
            audit_id=audit_id,
            status="succeeded",
            username=before["username"],
            action=data.action,
            after=after,
        )
    except Exception as exc:
        try:
            after = await get_oracle_user_lifecycle_state(connection, before["username"])
        except Exception:
            after = before
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            after=_state_for_audit(after),
            error=str(exc),
        )
        if isinstance(exc, AppError):
            raise
        raise AppError(
            "Oracle account action failed.",
            code="ORACLE_ACCOUNT_ACTION_FAILED",
            status_code=400,
        ) from exc
