from __future__ import annotations

from app.connectors.oracle_access_inspector import _is_powerful_system_privilege
from app.connectors.oracle_provisioning import normalize_oracle_identifier, quote_oracle_identifier
from app.connectors.oracle_role_management import (
    build_oracle_role_change_preview as connector_build_role_change_preview,
    create_oracle_role,
    drop_oracle_role,
    execute_oracle_role_statement,
    get_oracle_role_detail,
    get_oracle_roles,
    is_protected_role_name,
    oracle_role_exists,
)
from app.core.exceptions import AppError
from app.schemas.database_action import DatabaseActionRisk, DatabaseActionStatus
from app.schemas.oracle_dba import (
    OracleRoleChangeRequest,
    OracleRoleCreateRequest,
    OracleRoleDropRequest,
)
from app.schemas.user import UserResponse
from app.services.database_actions import finish_database_action, start_database_action
from app.services.oracle_dba import get_oracle_target


def _role_snapshot_for_audit(detail: dict) -> dict:
    return {
        "name": detail["name"],
        "manageable": detail.get("manageable", False),
        "member_count": len(detail.get("members", [])),
        "members": sorted(item["username"] for item in detail.get("members", [])),
        "child_roles": sorted(item["name"] for item in detail.get("child_roles", [])),
        "system_privileges": sorted(item["name"] for item in detail.get("system_privileges", [])),
        "object_privileges": sorted(
            f"{item['privilege']} ON {item['owner']}.{item['object_name']}"
            + (f".{item['column_name']}" if item.get("column_name") else "")
            for item in detail.get("object_privileges", [])
        )[:500],
    }


async def load_oracle_roles(database, connection_id: str):
    connection = await get_oracle_target(database, connection_id)
    return await get_oracle_roles(connection)


async def load_oracle_role_detail(database, connection_id: str, role_name: str):
    connection = await get_oracle_target(database, connection_id)
    return await get_oracle_role_detail(connection, role_name)


async def build_oracle_role_create_preview(database, connection_id: str, data: OracleRoleCreateRequest):
    connection = await get_oracle_target(database, connection_id)
    role_name = normalize_oracle_identifier(data.role_name, field_name="Role")
    if is_protected_role_name(role_name):
        raise AppError(
            f"{role_name} is reserved by DBAChum's protected Oracle role rules.",
            code="ORACLE_ROLE_NAME_PROTECTED",
            status_code=403,
        )
    exists = await oracle_role_exists(connection, role_name)
    return {
        "operation": "create_role",
        "role_name": role_name,
        "target": role_name,
        "statement": f"CREATE ROLE {quote_oracle_identifier(role_name)}",
        "ready_to_execute": not exists,
        "powerful": False,
        "warnings": ["This role already exists."] if exists else [],
    }


async def execute_oracle_role_create(
    database,
    connection_id: str,
    data: OracleRoleCreateRequest,
    current_user: UserResponse,
):
    connection = await get_oracle_target(database, connection_id)
    preview = await build_oracle_role_create_preview(database, connection_id, data)
    if not preview["ready_to_execute"]:
        raise AppError("Oracle role already exists.", code="ORACLE_ROLE_EXISTS", status_code=409)

    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine="oracle",
        action="oracle.role.create",
        operator=current_user,
        target=preview["role_name"],
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=data.request_reference,
        before={"exists": False},
        details={"statement": preview["statement"]},
    )
    try:
        await create_oracle_role(connection, preview["role_name"])
        detail = await get_oracle_role_detail(connection, preview["role_name"])
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.SUCCEEDED,
            after=_role_snapshot_for_audit(detail),
            details={"statement": preview["statement"]},
        )
        return {"audit_id": audit_id, "status": "succeeded", "role": detail}
    except Exception as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            error=str(exc),
            details={"statement": preview["statement"]},
        )
        raise


async def build_oracle_role_change_preview(
    database,
    connection_id: str,
    role_name: str,
    data: OracleRoleChangeRequest,
):
    connection = await get_oracle_target(database, connection_id)
    return await connector_build_role_change_preview(
        connection,
        role_name,
        operation=data.operation,
        value=data.value,
        username=data.username,
        owner=data.owner,
        object_name=data.object_name,
        privilege=data.privilege,
    )


async def execute_oracle_role_change(
    database,
    connection_id: str,
    role_name: str,
    data: OracleRoleChangeRequest,
    current_user: UserResponse,
):
    connection = await get_oracle_target(database, connection_id)
    preview = await connector_build_role_change_preview(
        connection,
        role_name,
        operation=data.operation,
        value=data.value,
        username=data.username,
        owner=data.owner,
        object_name=data.object_name,
        privilege=data.privilege,
    )
    if not preview["ready_to_execute"]:
        raise AppError(
            "The requested role change is already in the desired state.",
            code="ORACLE_ROLE_CHANGE_NOT_REQUIRED",
            status_code=409,
        )

    before_detail = await get_oracle_role_detail(connection, preview["role_name"])
    risk = DatabaseActionRisk.DANGEROUS if preview.get("powerful") else DatabaseActionRisk.SENSITIVE
    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine="oracle",
        action=f"oracle.role.{preview['operation']}",
        operator=current_user,
        target=preview["role_name"],
        risk=risk,
        request_reference=data.request_reference,
        before={
            "role": _role_snapshot_for_audit(before_detail),
            "change": {"target": preview["target"], "present": not preview["operation"].startswith("grant_")},
        },
        details={"statement": preview["statement"], "warnings": preview.get("warnings", [])},
    )
    try:
        await execute_oracle_role_statement(connection, preview["statement"])
        after_detail = await get_oracle_role_detail(connection, preview["role_name"])
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.SUCCEEDED,
            after={
                "role": _role_snapshot_for_audit(after_detail),
                "change": {"target": preview["target"], "present": preview["operation"].startswith("grant_")},
            },
            details={"statement": preview["statement"], "warnings": preview.get("warnings", [])},
        )
        return {"audit_id": audit_id, "status": "succeeded", "role": after_detail}
    except Exception as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            error=str(exc),
            details={"statement": preview["statement"], "warnings": preview.get("warnings", [])},
        )
        raise


async def build_oracle_role_drop_preview(database, connection_id: str, role_name: str):
    connection = await get_oracle_target(database, connection_id)
    detail = await get_oracle_role_detail(connection, role_name)
    if not detail.get("manageable"):
        raise AppError(
            f"Role {detail['name']} is Oracle-maintained or protected and cannot be dropped through DBAChum.",
            code="ORACLE_ROLE_PROTECTED",
            status_code=403,
        )
    warnings = []
    member_count = len(detail.get("members", []))
    parent_count = len(detail.get("parent_roles", []))
    if member_count:
        warnings.append(f"Dropping this role revokes it from {member_count} normal database user(s).")
    if parent_count:
        warnings.append(f"Dropping this role removes it from {parent_count} parent role(s).")
    if detail.get("system_privileges") or detail.get("object_privileges") or detail.get("child_roles"):
        warnings.append("All privileges and child-role grants owned by this role will be removed.")
    return {
        "role": detail,
        "statement": f"DROP ROLE {quote_oracle_identifier(detail['name'])}",
        "ready_to_execute": True,
        "warnings": warnings,
    }


async def execute_oracle_role_drop(
    database,
    connection_id: str,
    role_name: str,
    data: OracleRoleDropRequest,
    current_user: UserResponse,
):
    connection = await get_oracle_target(database, connection_id)
    preview = await build_oracle_role_drop_preview(database, connection_id, role_name)
    normalized_confirmation = normalize_oracle_identifier(data.confirm_role_name, field_name="Confirmation role")
    if normalized_confirmation != preview["role"]["name"]:
        raise AppError(
            "Type the exact role name to confirm deletion.",
            code="ORACLE_ROLE_DROP_CONFIRMATION_MISMATCH",
            status_code=400,
        )

    before = _role_snapshot_for_audit(preview["role"])
    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine="oracle",
        action="oracle.role.drop",
        operator=current_user,
        target=preview["role"]["name"],
        risk=DatabaseActionRisk.DANGEROUS,
        request_reference=data.request_reference,
        before=before,
        details={"statement": preview["statement"], "warnings": preview["warnings"]},
    )
    try:
        await drop_oracle_role(connection, preview["role"]["name"])
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.SUCCEEDED,
            after={"exists": False, "name": preview["role"]["name"]},
            details={"statement": preview["statement"], "warnings": preview["warnings"]},
        )
        return {"audit_id": audit_id, "status": "succeeded", "role_name": preview["role"]["name"]}
    except Exception as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            error=str(exc),
            details={"statement": preview["statement"], "warnings": preview["warnings"]},
        )
        raise
