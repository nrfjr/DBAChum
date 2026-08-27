from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from app.connectors.oracle_provisioning import (
    OracleUserReconcilePartialError,
    get_oracle_reference_user,
    is_sensitive_reference_role,
    normalize_oracle_identifier,
    reconcile_oracle_user,
    upsert_oracle_provisioning_row,
)
from app.core.exceptions import AppError
from app.schemas.database_action import (
    DatabaseActionRisk,
    DatabaseActionStatus,
)
from app.schemas.provisioning import (
    ProvisioningExecuteRequest,
    ProvisioningExecutionAccount,
    ProvisioningExecutionLdap,
    ProvisioningExecutionResponse,
    ProvisioningExecutionRole,
    ProvisioningExecutionTableStep,
)
from app.schemas.user import UserResponse
from app.services.database_actions import (
    finish_database_action,
    start_database_action,
)
from app.services.database_connections import get_database_connection
from app.services.ldap_directory import add_ldap_entry_from_ldif
from app.services.ldap_ldif import (
    DEFAULT_LDIF_TEMPLATE,
    normalize_employee_id,
    normalize_person_name,
    render_ldif,
)
from app.services.provisioning import (
    effective_match_columns,
    get_ldap_profile_document,
    get_provisioning_profile,
)
from app.services.provisioning_preview import build_provisioning_preview


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _display_value(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc) or exc.__class__.__name__


def _extract_ldif_dn(content: str | None) -> str | None:
    if not content:
        return None
    for line in content.splitlines():
        if line.lower().startswith("dn:"):
            return line.split(":", 1)[1].strip() or None
    return None


def _is_sensitive_column(column_name: str) -> bool:
    normalized = str(column_name).strip().upper()
    return any(token in normalized for token in ("PASSWORD", "PASSWD", "PWD", "SECRET", "TOKEN"))


def _sensitive_step_columns(step: dict) -> set[str]:
    sensitive: set[str] = set()
    for mapping in step.get("mappings") or []:
        column = str(mapping.get("column_name", "")).strip().upper()
        if not column:
            continue
        if _is_sensitive_column(column) or (
            mapping.get("value_kind") == "generated"
            and mapping.get("value_key") == "password"
        ):
            sensitive.add(column)
    return sensitive


def _redact_values(values: dict[str, object], sensitive_columns: set[str]) -> dict[str, object]:
    return {
        key: "<redacted>" if key.upper() in sensitive_columns else _display_value(value)
        for key, value in values.items()
    }


def _profile_snapshot(profile: dict) -> dict:
    """Persist retry-safe profile structure without storing password-like custom values."""
    steps = deepcopy(profile.get("table_steps") or [])
    for step in steps:
        for mapping in step.get("mappings") or []:
            column = str(mapping.get("column_name", "")).strip().upper()
            if _is_sensitive_column(column) and mapping.get("value_kind") == "custom":
                mapping["custom_value"] = None
                mapping["value_redacted"] = True
    return {
        "name": profile.get("name"),
        "schema_connection_id": profile.get("schema_connection_id"),
        "ldap_enabled": bool(profile.get("ldap_enabled")),
        "ldap_profile_id": profile.get("ldap_profile_id"),
        "table_steps": steps,
        "updated_at": profile.get("updated_at"),
    }


def _resolve_step_values(
    step: dict,
    *,
    form_values: dict[str, object],
    generated_values: dict[str, object],
):
    insert_values: dict[str, object] = {}
    update_values: dict[str, object] = {}
    sequence_columns: dict[str, str] = {}
    redacted_values: dict[str, object] = {}

    for mapping in step.get("mappings") or []:
        kind = mapping.get("value_kind", "omit")
        column = str(mapping.get("column_name", "")).strip().upper()
        if not column or kind == "omit":
            continue

        if kind == "sequence":
            sequence_columns[column] = str(mapping.get("value_key", "")).strip().upper()
            redacted_values[column] = f"{step['owner']}.{sequence_columns[column]}.NEXTVAL"
            continue

        if kind == "form":
            value = form_values.get(mapping.get("value_key"))
        elif kind == "generated":
            value = generated_values.get(mapping.get("value_key"))
        elif kind == "custom":
            value = mapping.get("custom_value")
        elif kind == "null":
            value = None
        else:
            continue

        insert_values[column] = value
        update_values[column] = value
        if _is_sensitive_column(column) or (
            kind == "generated" and mapping.get("value_key") == "password"
        ):
            redacted_values[column] = "<redacted>"
        else:
            redacted_values[column] = value

    return insert_values, update_values, sequence_columns, redacted_values


async def _update_run(database, run_id, **fields):
    fields["updated_at"] = datetime.now(timezone.utc)
    await database.provisioning_runs.update_one(
        {"_id": run_id},
        {"$set": fields},
    )


async def execute_provisioning_profile(
    database,
    parent_connection_id: str,
    profile_id: str,
    data: ProvisioningExecuteRequest,
    operator: UserResponse,
    *,
    requester_ip: str | None = None,
) -> ProvisioningExecutionResponse:
    """Execute one reviewed provisioning profile from its parent DB context.

    Phase 4B intentionally uses controlled partial execution rather than
    pretending Oracle DDL plus multiple application connections can share one
    atomic transaction. Each successful table step commits independently and is
    persisted immediately in provisioning_runs for future retry/deprovisioning.
    """
    preview = await build_provisioning_preview(
        database,
        profile_id,
        data,
        operator,
        requester_ip=requester_ip,
        parent_connection_id=parent_connection_id,
    )
    if not preview.ready_to_execute:
        raise AppError(
            "Provisioning preview contains a conflict. Resolve it before execution.",
            code="PROVISIONING_PREVIEW_CONFLICT",
            status_code=409,
        )

    profile = await get_provisioning_profile(database, profile_id)
    parent_connection = await get_database_connection(database, parent_connection_id)
    username = preview.username

    first_name = normalize_person_name(data.first_name)
    middle_name = normalize_person_name(data.middle_name)
    last_name = normalize_person_name(data.last_name)
    employee_id = normalize_employee_id(data.employee_id)
    reference_username = _clean_optional(data.reference_user)
    if reference_username:
        reference_username = normalize_oracle_identifier(
            reference_username,
            field_name="Reference username",
        )

    selected_roles = [
        normalize_oracle_identifier(role, field_name="Role")
        for role in data.roles
    ]
    if len(selected_roles) != len(set(selected_roles)):
        raise AppError(
            "Duplicate roles are not allowed.",
            code="PROVISIONING_DUPLICATE_ROLE",
            status_code=400,
        )
    sensitive_roles = [role for role in selected_roles if is_sensitive_reference_role(role)]
    if sensitive_roles:
        raise AppError(
            "Sensitive roles cannot be copied automatically: " + ", ".join(sensitive_roles),
            code="PROVISIONING_SENSITIVE_ROLE_BLOCKED",
            status_code=400,
        )

    if reference_username:
        reference = await get_oracle_reference_user(parent_connection, reference_username)
        allowed_roles = {
            role["name"].upper()
            for role in reference.get("roles", [])
            if not role.get("sensitive")
            and not is_sensitive_reference_role(role.get("name", ""))
        }
        invalid_roles = [role for role in selected_roles if role not in allowed_roles]
        if invalid_roles:
            raise AppError(
                "Selected roles are not safe roles on the reviewed reference user: "
                + ", ".join(invalid_roles),
                code="PROVISIONING_ROLE_NOT_ON_REFERENCE",
                status_code=400,
            )
    elif selected_roles:
        raise AppError(
            "Roles can only be copied when a reference user is selected.",
            code="PROVISIONING_REFERENCE_REQUIRED_FOR_ROLES",
            status_code=400,
        )

    now = datetime.now(timezone.utc)
    form_values: dict[str, object] = {
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "employee_id": employee_id,
        "reference_user": reference_username,
        "requestor": _clean_optional(data.requestor),
        "request_reference": _clean_optional(data.request_reference),
        "remarks": _clean_optional(data.remarks),
    }
    generated_values: dict[str, object] = {
        "username": username,
        "password": data.password,
        "operator_username": operator.username,
        "requester_ip": requester_ip,
        "current_datetime": now,
    }

    ldap_snapshot = None
    if profile.get("ldap_enabled"):
        ldap_document = await get_ldap_profile_document(
            database, profile["ldap_profile_id"]
        )
        ldap_snapshot = {
            "profile_id": profile.get("ldap_profile_id"),
            "profile_name": ldap_document.get("name", "LDAP"),
            "base_dn": ldap_document.get("base_dn", ""),
            "ldif_template": ldap_document.get("ldif_template") or DEFAULT_LDIF_TEMPLATE,
        }

    run_document = {
        "parent_connection_id": parent_connection_id,
        "parent_connection_name": parent_connection.get("name", parent_connection_id),
        "username": username,
        "employee_id": employee_id,
        "profile_id": profile_id,
        "profile_name": profile.get("name", profile_id),
        "profile_updated_at": profile.get("updated_at"),
        "status": "running",
        "operator_user_id": operator.id,
        "operator_username": operator.username,
        "requester_ip": requester_ip,
        "request_reference": _clean_optional(data.request_reference),
        "requestor": _clean_optional(data.requestor),
        "remarks": _clean_optional(data.remarks),
        "reference_user": reference_username,
        "account_existed_before": preview.account_exists,
        "input_snapshot": {
            **form_values,
            "username": username,
        },
        "desired_roles": selected_roles,
        "account_settings": {
            "default_tablespace": _clean_optional(data.default_tablespace),
            "temporary_tablespace": _clean_optional(data.temporary_tablespace),
            "oracle_profile": _clean_optional(data.oracle_profile),
        },
        "generated_context": {
            "username": username,
            "operator_username": operator.username,
            "requester_ip": requester_ip,
            "current_datetime": now,
        },
        "profile_snapshot": _profile_snapshot(profile),
        "ldap_snapshot": ldap_snapshot,
        "retry_attempts": [],
        "retry_count": 0,
        "account": None,
        "roles": [],
        "table_steps": [],
        "ldap": None,
        "error": None,
        "started_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    inserted = await database.provisioning_runs.insert_one(run_document)
    run_id = inserted.inserted_id

    audit_id = await start_database_action(
        database,
        connection_id=parent_connection_id,
        engine="oracle",
        action="provision_user",
        target=username,
        operator=operator,
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=_clean_optional(data.request_reference),
        before={"account_exists": preview.account_exists},
        details={
            "provisioning_run_id": str(run_id),
            "profile_id": profile_id,
            "profile_name": profile.get("name"),
            "employee_id": employee_id,
            "requester_ip": requester_ip,
            "reference_user": reference_username,
            "selected_roles": selected_roles,
            "password_stored_in_audit": False,
        },
    )

    account = ProvisioningExecutionAccount(action="failed")
    role_results: list[ProvisioningExecutionRole] = []
    step_results: list[ProvisioningExecutionTableStep] = []
    ldap_result = ProvisioningExecutionLdap(
        enabled=bool(profile.get("ldap_enabled")),
        action="not_run" if profile.get("ldap_enabled") else None,
        profile_id=profile.get("ldap_profile_id"),
    )
    ldif_content: str | None = None
    mutated = False
    overall_error: str | None = None

    try:
        try:
            account_raw = await reconcile_oracle_user(
                parent_connection,
                username=username,
                password=data.password,
                roles=selected_roles,
                default_tablespace=_clean_optional(data.default_tablespace),
                temporary_tablespace=_clean_optional(data.temporary_tablespace),
                profile=_clean_optional(data.oracle_profile),
            )
        except OracleUserReconcilePartialError as exc:
            account = ProvisioningExecutionAccount(
                action=("created" if exc.account_action == "created" else "altered"),
                password_applied=True,
                default_tablespace=_clean_optional(data.default_tablespace),
                temporary_tablespace=_clean_optional(data.temporary_tablespace),
                oracle_profile=_clean_optional(data.oracle_profile),
                error=str(exc),
            )
            role_results = [
                ProvisioningExecutionRole(name=role, action="granted")
                for role in exc.roles_added
            ] + [
                ProvisioningExecutionRole(name=role, action="already_present")
                for role in exc.roles_already_present
            ]
            mutated = True
            raise AppError(
                "Oracle account was changed, but role reconciliation failed: " + str(exc),
                code="PROVISIONING_ORACLE_ACCOUNT_PARTIAL",
                status_code=409,
            ) from exc

        account = ProvisioningExecutionAccount(
            action=account_raw["account_action"],
            password_applied=account_raw["password_applied"],
            default_tablespace=account_raw.get("default_tablespace"),
            temporary_tablespace=account_raw.get("temporary_tablespace"),
            oracle_profile=account_raw.get("profile"),
        )
        role_results = [
            ProvisioningExecutionRole(name=role, action="granted")
            for role in account_raw.get("roles_added", [])
        ] + [
            ProvisioningExecutionRole(name=role, action="already_present")
            for role in account_raw.get("roles_already_present", [])
        ]
        mutated = True
        await _update_run(
            database,
            run_id,
            account=account.model_dump(mode="python"),
            roles=[role.model_dump(mode="python") for role in role_results],
        )

        for index, step in enumerate(profile.get("table_steps") or [], start=1):
            step_connection = await get_database_connection(database, step["connection_id"])
            insert_values, update_values, sequence_columns, redacted_values = _resolve_step_values(
                step,
                form_values=form_values,
                generated_values=generated_values,
            )
            match_columns = effective_match_columns(step)
            match_values = {
                column: insert_values.get(column)
                for column in match_columns
            }
            missing_match = [
                column for column, value in match_values.items()
                if value is None or (isinstance(value, str) and not value.strip())
            ]
            if missing_match:
                raise AppError(
                    "Upsert match values are missing for: " + ", ".join(missing_match),
                    code="PROVISIONING_MATCH_VALUE_REQUIRED",
                    status_code=400,
                )

            sensitive_columns = _sensitive_step_columns(step)
            try:
                upsert = await upsert_oracle_provisioning_row(
                    step_connection,
                    owner=step["owner"],
                    table_name=step["table_name"],
                    match_values=match_values,
                    insert_values=insert_values,
                    update_values=update_values,
                    sequence_columns=sequence_columns,
                )
                generated = {
                    key: _display_value(value)
                    for key, value in (upsert.get("generated_values") or {}).items()
                }
                sensitive_columns = _sensitive_step_columns(step)
                step_result = ProvisioningExecutionTableStep(
                    index=index,
                    name=step["name"],
                    connection_id=step["connection_id"],
                    connection_name=step_connection.get("name", step["connection_id"]),
                    owner=step["owner"],
                    table_name=step["table_name"],
                    action=upsert["action"],
                    match_values=_redact_values(match_values, sensitive_columns),
                    generated_values={
                        key: "<redacted>" if key.upper() in sensitive_columns else value
                        for key, value in generated.items()
                    },
                    before_values=_redact_values(
                        upsert.get("before_values") or {}, sensitive_columns
                    ),
                    after_values=_redact_values(
                        upsert.get("after_values") or {}, sensitive_columns
                    ),
                    sensitive_columns=sorted(sensitive_columns),
                )
                step_results.append(step_result)
                mutated = True
                await _update_run(
                    database,
                    run_id,
                    table_steps=[item.model_dump(mode="python") for item in step_results],
                    last_step_values={
                        "index": index,
                        "values": {
                            key: _display_value(value)
                            for key, value in redacted_values.items()
                        },
                    },
                )
            except Exception as exc:
                action = (
                    "conflict"
                    if isinstance(exc, AppError)
                    and getattr(exc, "code", "") == "PROVISIONING_UPSERT_CONFLICT"
                    else "failed"
                )
                step_results.append(
                    ProvisioningExecutionTableStep(
                        index=index,
                        name=step["name"],
                        connection_id=step["connection_id"],
                        connection_name=step_connection.get("name", step["connection_id"]),
                        owner=step["owner"],
                        table_name=step["table_name"],
                        action=action,
                        match_values=_redact_values(match_values, sensitive_columns),
                        sensitive_columns=sorted(sensitive_columns),
                        error=_safe_error(exc),
                    )
                )
                for remaining_index, remaining in enumerate(
                    (profile.get("table_steps") or [])[index:],
                    start=index + 1,
                ):
                    remaining_connection = await get_database_connection(
                        database, remaining["connection_id"]
                    )
                    step_results.append(
                        ProvisioningExecutionTableStep(
                            index=remaining_index,
                            name=remaining["name"],
                            connection_id=remaining["connection_id"],
                            connection_name=remaining_connection.get(
                                "name", remaining["connection_id"]
                            ),
                            owner=remaining["owner"],
                            table_name=remaining["table_name"],
                            action="not_run",
                            sensitive_columns=sorted(_sensitive_step_columns(remaining)),
                        )
                    )
                raise

        if profile.get("ldap_enabled"):
            try:
                ldap_profile = await get_ldap_profile_document(
                    database, profile["ldap_profile_id"]
                )
                ldif_content = render_ldif(
                    ldap_profile.get("ldif_template") or DEFAULT_LDIF_TEMPLATE,
                    username=username,
                    password=data.password,
                    first_name=first_name,
                    middle_name=middle_name,
                    last_name=last_name,
                    employee_id=employee_id,
                    base_dn=ldap_profile.get("base_dn", ""),
                )
                ldap_write = await add_ldap_entry_from_ldif(ldap_profile, ldif_content)
                ldap_result = ProvisioningExecutionLdap(
                    enabled=True,
                    action=ldap_write["action"],
                    profile_id=profile["ldap_profile_id"],
                    profile_name=ldap_profile.get("name", "LDAP"),
                    filename=f"{username}.ldif",
                    content=ldif_content,
                    dn=ldap_write["dn"],
                )
                if ldap_write["action"] == "created":
                    mutated = True
                await _update_run(
                    database,
                    run_id,
                    ldap={
                        **ldap_result.model_dump(mode="python"),
                        "content": None,
                    },
                )
            except Exception as exc:
                ldap_result = ProvisioningExecutionLdap(
                    enabled=True,
                    action="failed",
                    profile_id=profile.get("ldap_profile_id"),
                    error=_safe_error(exc),
                )
                raise

    except Exception as exc:
        overall_error = _safe_error(exc)
        status = "partial" if mutated else "failed"
        completed_at = datetime.now(timezone.utc)
        await _update_run(
            database,
            run_id,
            status=status,
            account=account.model_dump(mode="python"),
            roles=[role.model_dump(mode="python") for role in role_results],
            table_steps=[step.model_dump(mode="python") for step in step_results],
            ldap={
                **ldap_result.model_dump(mode="python"),
                "content": None,
            },
            error=overall_error,
            completed_at=completed_at,
        )
        await finish_database_action(
            database,
            audit_id,
            status=(
                DatabaseActionStatus.PARTIAL
                if status == "partial"
                else DatabaseActionStatus.FAILED
            ),
            after={
                "provisioning_run_id": str(run_id),
                "account_action": account.action,
                "table_steps_completed": len(
                    [step for step in step_results if step.action in {"inserted", "updated", "unchanged"}]
                ),
            },
            error=overall_error,
            details={
                "provisioning_run_id": str(run_id),
                "profile_id": profile_id,
                "profile_name": profile.get("name"),
                "password_stored_in_audit": False,
            },
        )
        return ProvisioningExecutionResponse(
            run_id=str(run_id),
            audit_id=audit_id,
            status=status,
            username=username,
            profile_id=profile_id,
            profile_name=profile.get("name", profile_id),
            schema_connection_id=parent_connection_id,
            schema_connection_name=parent_connection.get("name", parent_connection_id),
            requester_ip=requester_ip,
            account=account,
            roles=role_results,
            table_steps=step_results,
            ldap=ldap_result,
            error=overall_error,
        )

    completed_at = datetime.now(timezone.utc)
    await _update_run(
        database,
        run_id,
        status="succeeded",
        account=account.model_dump(mode="python"),
        roles=[role.model_dump(mode="python") for role in role_results],
        table_steps=[step.model_dump(mode="python") for step in step_results],
        ldap={
            **ldap_result.model_dump(mode="python"),
            "content": None,
        },
        error=None,
        completed_at=completed_at,
    )
    await finish_database_action(
        database,
        audit_id,
        status=DatabaseActionStatus.SUCCEEDED,
        after={
            "provisioning_run_id": str(run_id),
            "account_action": account.action,
            "table_steps_completed": len(step_results),
            "ldap_generated": ldap_result.action == "generated",
        },
        details={
            "provisioning_run_id": str(run_id),
            "profile_id": profile_id,
            "profile_name": profile.get("name"),
            "employee_id": employee_id,
            "requester_ip": requester_ip,
            "password_stored_in_audit": False,
        },
    )

    return ProvisioningExecutionResponse(
        run_id=str(run_id),
        audit_id=audit_id,
        status="succeeded",
        username=username,
        profile_id=profile_id,
        profile_name=profile.get("name", profile_id),
        schema_connection_id=parent_connection_id,
        schema_connection_name=parent_connection.get("name", parent_connection_id),
        requester_ip=requester_ip,
        account=account,
        roles=role_results,
        table_steps=step_results,
        ldap=ldap_result,
        error=None,
    )
