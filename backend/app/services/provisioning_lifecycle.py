from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId

from app.connectors.oracle_provisioning import (
    OracleUserReconcilePartialError,
    fetch_oracle_provisioning_row,
    oracle_user_exists,
    reconcile_oracle_roles,
    reconcile_oracle_user,
    upsert_oracle_provisioning_row,
)
from app.core.exceptions import AppError
from app.schemas.database_action import DatabaseActionRisk, DatabaseActionStatus
from app.schemas.provisioning import (
    ProvisioningDeprovisionPreviewItem,
    ProvisioningDeprovisionPreviewResponse,
    ProvisioningExecutionAccount,
    ProvisioningExecutionLdap,
    ProvisioningExecutionResponse,
    ProvisioningExecutionRole,
    ProvisioningExecutionTableStep,
    ProvisioningRetryAttempt,
    ProvisioningRetryRequest,
    ProvisioningRetryRequirement,
    ProvisioningRunDetail,
    ProvisioningRunSummary,
)
from app.schemas.user import UserResponse
from app.services.database_actions import finish_database_action, start_database_action
from app.services.database_connections import get_database_connection
from app.services.ldap_directory import add_ldap_entry_from_ldif
from app.services.ldap_ldif import DEFAULT_LDIF_TEMPLATE, render_ldif
from app.services.provisioning import effective_match_columns, get_ldap_profile_document
from app.services.provisioning_execution import (
    _display_value,
    _extract_ldif_dn,
    _is_sensitive_column,
    _redact_values,
    _resolve_step_values,
    _safe_error,
    _sensitive_step_columns,
)


COMPLETED_TABLE_ACTIONS = {"inserted", "updated", "unchanged"}
COMPLETED_LDAP_ACTIONS = {"created", "already_present"}


def _parse_run_id(run_id: str) -> ObjectId:
    try:
        return ObjectId(run_id)
    except Exception as exc:
        raise AppError(
            "Provisioning run not found.",
            code="PROVISIONING_RUN_NOT_FOUND",
            status_code=404,
        ) from exc


def _model_account(value: dict | None) -> ProvisioningExecutionAccount | None:
    return ProvisioningExecutionAccount(**value) if value else None


def _model_roles(values: list[dict] | None) -> list[ProvisioningExecutionRole]:
    return [ProvisioningExecutionRole(**value) for value in (values or [])]


def _model_steps(values: list[dict] | None) -> list[ProvisioningExecutionTableStep]:
    return [ProvisioningExecutionTableStep(**value) for value in (values or [])]


def _model_ldap(value: dict | None) -> ProvisioningExecutionLdap | None:
    return ProvisioningExecutionLdap(**value) if value else None


def _pending_state(document: dict) -> tuple[list[str], bool, bool, str | None]:
    if document.get("status") == "succeeded":
        return [], False, False, "Provisioning already completed successfully."

    profile = document.get("profile_snapshot")
    inputs = document.get("input_snapshot")
    if not profile or not inputs:
        return [], False, False, (
            "This run predates Phase 4C lifecycle snapshots and cannot be safely retried automatically."
        )

    pending: list[str] = []
    password_required = False
    retryable = True
    reason = None

    account = document.get("account") or {}
    if not account or account.get("action") == "failed":
        pending.append("Oracle account")
        password_required = True

    desired_roles = [str(role).upper() for role in (document.get("desired_roles") or [])]
    recorded_roles = {
        str(role.get("name", "")).upper()
        for role in (document.get("roles") or [])
        if role.get("action") in {"granted", "already_present"}
    }
    missing_roles = [role for role in desired_roles if role not in recorded_roles]
    if missing_roles:
        pending.append("Roles: " + ", ".join(missing_roles))

    current_steps = {
        int(step.get("index")): step
        for step in (document.get("table_steps") or [])
        if step.get("index") is not None
    }
    for index, step in enumerate(profile.get("table_steps") or [], start=1):
        current = current_steps.get(index)
        if current and current.get("action") in COMPLETED_TABLE_ACTIONS:
            continue
        pending.append(f"Table step {index}: {step.get('name', 'Unnamed step')}")
        for mapping in step.get("mappings") or []:
            if mapping.get("value_kind") == "generated" and mapping.get("value_key") == "password":
                password_required = True
            if (
                mapping.get("value_kind") == "custom"
                and mapping.get("value_redacted")
            ):
                retryable = False
                reason = (
                    "A pending table step used a custom value in a password-like column. "
                    "That value was intentionally not persisted, so the step requires manual review."
                )

    if profile.get("ldap_enabled"):
        ldap = document.get("ldap") or {}
        if ldap.get("action") not in COMPLETED_LDAP_ACTIONS:
            pending.append("LDAP entry")
            template = (document.get("ldap_snapshot") or {}).get("ldif_template") or ""
            if "<PASSWORD>" in template.upper():
                password_required = True

    if not pending:
        retryable = False
        reason = "No incomplete lifecycle steps remain."

    return pending, password_required, retryable, reason


def _summary(document: dict) -> ProvisioningRunSummary:
    pending, password_required, retryable, _ = _pending_state(document)
    return ProvisioningRunSummary(
        run_id=str(document["_id"]),
        status=document.get("status", "failed"),
        username=document.get("username", ""),
        employee_id=document.get("employee_id"),
        profile_id=document.get("profile_id", ""),
        profile_name=document.get("profile_name", document.get("profile_id", "")),
        operator_username=document.get("operator_username", "unknown"),
        request_reference=document.get("request_reference"),
        started_at=document.get("started_at") or datetime.now(timezone.utc),
        completed_at=document.get("completed_at"),
        retry_count=int(document.get("retry_count", len(document.get("retry_attempts") or []))),
        retryable=retryable,
        password_required=password_required,
    )


def _detail(document: dict) -> ProvisioningRunDetail:
    summary = _summary(document)
    return ProvisioningRunDetail(
        **summary.model_dump(mode="python"),
        schema_connection_id=document.get("parent_connection_id", ""),
        schema_connection_name=document.get("parent_connection_name", document.get("parent_connection_id", "")),
        requester_ip=document.get("requester_ip"),
        requestor=document.get("requestor"),
        remarks=document.get("remarks"),
        reference_user=document.get("reference_user"),
        account=_model_account(document.get("account")),
        roles=_model_roles(document.get("roles")),
        table_steps=_model_steps(document.get("table_steps")),
        ldap=_model_ldap(document.get("ldap")),
        error=document.get("error"),
        retry_attempts=[
            ProvisioningRetryAttempt(**attempt)
            for attempt in (document.get("retry_attempts") or [])
        ],
    )


async def _get_run_document(database, parent_connection_id: str, run_id: str) -> dict:
    document = await database.provisioning_runs.find_one(
        {"_id": _parse_run_id(run_id), "parent_connection_id": parent_connection_id}
    )
    if document is None:
        raise AppError(
            "Provisioning run not found for this database.",
            code="PROVISIONING_RUN_NOT_FOUND",
            status_code=404,
        )
    return document


async def list_provisioning_runs(
    database,
    parent_connection_id: str,
    *,
    limit: int = 50,
) -> list[ProvisioningRunSummary]:
    safe_limit = max(1, min(limit, 100))
    cursor = (
        database.provisioning_runs.find({"parent_connection_id": parent_connection_id})
        .sort("started_at", -1)
    )
    documents = await cursor.to_list(safe_limit)
    return [_summary(document) for document in documents]


async def clear_provisioning_runs(
    database,
    parent_connection_id: str,
    *,
    run_ids: list[str] | None = None,
    clear_all: bool = False,
) -> dict[str, int]:

    terminal_filter = {"$in": ["succeeded", "partial", "failed"]}

    if clear_all:
        result = await database.provisioning_runs.delete_many(
            {
                "parent_connection_id": parent_connection_id,
                "status": terminal_filter,
            }
        )
        return {
            "deleted_count": int(result.deleted_count),
            "skipped_count": 0,
        }

    raw_ids = run_ids or []
    object_ids: list[ObjectId] = []
    for run_id in raw_ids:
        object_ids.append(_parse_run_id(run_id))

    if not object_ids:
        return {"deleted_count": 0, "skipped_count": 0}

    result = await database.provisioning_runs.delete_many(
        {
            "_id": {"$in": object_ids},
            "parent_connection_id": parent_connection_id,
            "status": terminal_filter,
        }
    )
    deleted_count = int(result.deleted_count)
    return {
        "deleted_count": deleted_count,
        "skipped_count": max(0, len(object_ids) - deleted_count),
    }


async def get_provisioning_run(
    database,
    parent_connection_id: str,
    run_id: str,
) -> ProvisioningRunDetail:
    return _detail(await _get_run_document(database, parent_connection_id, run_id))


async def get_retry_requirement(
    database,
    parent_connection_id: str,
    run_id: str,
) -> ProvisioningRetryRequirement:
    document = await _get_run_document(database, parent_connection_id, run_id)
    pending, password_required, retryable, reason = _pending_state(document)
    return ProvisioningRetryRequirement(
        retryable=retryable,
        password_required=password_required,
        pending=pending,
        reason=reason,
    )


def _replace_step(steps: list[ProvisioningExecutionTableStep], replacement: ProvisioningExecutionTableStep):
    for index, current in enumerate(steps):
        if current.index == replacement.index:
            steps[index] = replacement
            return
    steps.append(replacement)
    steps.sort(key=lambda item: item.index)


def _merged_roles(
    desired_roles: list[str],
    existing: list[ProvisioningExecutionRole],
    roles_added: list[str],
    roles_already_present: list[str],
) -> list[ProvisioningExecutionRole]:
    previous = {role.name.upper(): role for role in existing}
    added = {role.upper() for role in roles_added}
    already = {role.upper() for role in roles_already_present}
    result: list[ProvisioningExecutionRole] = []
    for role in desired_roles:
        key = role.upper()
        if key in previous:
            result.append(previous[key])
        elif key in added:
            result.append(ProvisioningExecutionRole(name=role, action="granted"))
        elif key in already:
            result.append(ProvisioningExecutionRole(name=role, action="already_present"))
    return result


def _all_completed(
    profile: dict,
    account: ProvisioningExecutionAccount | None,
    roles: list[ProvisioningExecutionRole],
    steps: list[ProvisioningExecutionTableStep],
    ldap: ProvisioningExecutionLdap | None,
    desired_roles: list[str],
) -> bool:
    if account is None or account.action == "failed":
        return False
    represented_roles = {role.name.upper() for role in roles}
    if any(role.upper() not in represented_roles for role in desired_roles):
        return False
    by_index = {step.index: step for step in steps}
    for index, _step in enumerate(profile.get("table_steps") or [], start=1):
        if by_index.get(index) is None or by_index[index].action not in COMPLETED_TABLE_ACTIONS:
            return False
    if profile.get("ldap_enabled") and (ldap is None or ldap.action not in COMPLETED_LDAP_ACTIONS):
        return False
    return True


async def retry_provisioning_run(
    database,
    parent_connection_id: str,
    run_id: str,
    data: ProvisioningRetryRequest,
    operator: UserResponse,
    *,
    requester_ip: str | None = None,
) -> ProvisioningExecutionResponse:
    document = await _get_run_document(database, parent_connection_id, run_id)
    pending, password_required, retryable, reason = _pending_state(document)
    if not retryable:
        raise AppError(
            reason or "This provisioning run cannot be retried.",
            code="PROVISIONING_RETRY_NOT_AVAILABLE",
            status_code=409,
        )
    if password_required and not data.password:
        raise AppError(
            "The original provisioning password is required only for the remaining password-dependent step(s). Enter it to continue the retry.",
            code="PROVISIONING_RETRY_PASSWORD_REQUIRED",
            status_code=400,
        )

    profile = document["profile_snapshot"]
    inputs = document["input_snapshot"]
    username = document["username"]
    desired_roles = [str(role).upper() for role in (document.get("desired_roles") or [])]
    account_settings = document.get("account_settings") or {}
    generated_context = dict(document.get("generated_context") or {})
    generated_context["username"] = username
    generated_context["password"] = data.password

    parent_connection = await get_database_connection(database, parent_connection_id)
    account = _model_account(document.get("account"))
    roles = _model_roles(document.get("roles"))
    steps = _model_steps(document.get("table_steps"))
    ldap = _model_ldap(document.get("ldap")) or ProvisioningExecutionLdap(
        enabled=bool(profile.get("ldap_enabled")),
        action="not_run" if profile.get("ldap_enabled") else None,
        profile_id=profile.get("ldap_profile_id"),
    )

    attempt_started = datetime.now(timezone.utc)
    audit_id = await start_database_action(
        database,
        connection_id=parent_connection_id,
        engine="oracle",
        action="retry_provision_user",
        target=username,
        operator=operator,
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=document.get("request_reference"),
        before={"provisioning_run_id": run_id, "status": document.get("status"), "pending": pending},
        details={
            "provisioning_run_id": run_id,
            "password_stored_in_audit": False,
            "retry_password_required": password_required,
        },
    )

    await database.provisioning_runs.update_one(
        {"_id": document["_id"]},
        {"$set": {"status": "running", "error": None, "updated_at": attempt_started}},
    )

    current_error: str | None = None
    retry_mutated = False
    ldif_content: str | None = None

    try:
        if account is None or account.action == "failed":
            try:
                account_raw = await reconcile_oracle_user(
                    parent_connection,
                    username=username,
                    password=data.password or "",
                    roles=desired_roles,
                    default_tablespace=account_settings.get("default_tablespace"),
                    temporary_tablespace=account_settings.get("temporary_tablespace"),
                    profile=account_settings.get("oracle_profile"),
                )
            except OracleUserReconcilePartialError as exc:
                account = ProvisioningExecutionAccount(
                    action=("created" if exc.account_action == "created" else "altered"),
                    password_applied=True,
                    default_tablespace=account_settings.get("default_tablespace"),
                    temporary_tablespace=account_settings.get("temporary_tablespace"),
                    oracle_profile=account_settings.get("oracle_profile"),
                    error=str(exc),
                )
                roles = _merged_roles(
                    desired_roles,
                    roles,
                    exc.roles_added,
                    exc.roles_already_present,
                )
                retry_mutated = True
                raise AppError(
                    "Oracle account was changed during retry, but role reconciliation failed: " + str(exc),
                    code="PROVISIONING_ORACLE_ACCOUNT_PARTIAL",
                    status_code=409,
                ) from exc

            account = ProvisioningExecutionAccount(
                action=account_raw["account_action"],
                password_applied=account_raw.get("password_applied", False),
                default_tablespace=account_raw.get("default_tablespace"),
                temporary_tablespace=account_raw.get("temporary_tablespace"),
                oracle_profile=account_raw.get("profile"),
            )
            roles = _merged_roles(
                desired_roles,
                roles,
                account_raw.get("roles_added", []),
                account_raw.get("roles_already_present", []),
            )
            retry_mutated = True
        else:
            represented = {role.name.upper() for role in roles}
            missing_roles = [role for role in desired_roles if role not in represented]
            if missing_roles:
                role_raw = await reconcile_oracle_roles(
                    parent_connection,
                    username=username,
                    roles=missing_roles,
                )
                roles = _merged_roles(
                    desired_roles,
                    roles,
                    role_raw.get("roles_added", []),
                    role_raw.get("roles_already_present", []),
                )
                retry_mutated = retry_mutated or bool(role_raw.get("roles_added"))
                if account.error:
                    account.error = None

        await database.provisioning_runs.update_one(
            {"_id": document["_id"]},
            {"$set": {
                "account": account.model_dump(mode="python") if account else None,
                "roles": [role.model_dump(mode="python") for role in roles],
                "updated_at": datetime.now(timezone.utc),
            }},
        )

        current_by_index = {step.index: step for step in steps}
        for index, step in enumerate(profile.get("table_steps") or [], start=1):
            previous = current_by_index.get(index)
            if previous and previous.action in COMPLETED_TABLE_ACTIONS:
                continue

            step_connection = await get_database_connection(database, step["connection_id"])
            insert_values, update_values, sequence_columns, _redacted = _resolve_step_values(
                step,
                form_values=inputs,
                generated_values=generated_context,
            )
            match_columns = effective_match_columns(step)
            match_values = {column: insert_values.get(column) for column in match_columns}
            missing_match = [
                column for column, value in match_values.items()
                if value is None or (isinstance(value, str) and not value.strip())
            ]
            if missing_match:
                raise AppError(
                    "Retry match values are missing for: " + ", ".join(missing_match),
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
                replacement = ProvisioningExecutionTableStep(
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
                    before_values=_redact_values(upsert.get("before_values") or {}, sensitive_columns),
                    after_values=_redact_values(upsert.get("after_values") or {}, sensitive_columns),
                    sensitive_columns=sorted(sensitive_columns),
                )
                _replace_step(steps, replacement)
                current_by_index[index] = replacement
                retry_mutated = retry_mutated or replacement.action in {"inserted", "updated"}
                await database.provisioning_runs.update_one(
                    {"_id": document["_id"]},
                    {"$set": {
                        "table_steps": [item.model_dump(mode="python") for item in steps],
                        "updated_at": datetime.now(timezone.utc),
                    }},
                )
            except Exception as exc:
                action = (
                    "conflict"
                    if isinstance(exc, AppError)
                    and getattr(exc, "code", "") == "PROVISIONING_UPSERT_CONFLICT"
                    else "failed"
                )
                replacement = ProvisioningExecutionTableStep(
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
                _replace_step(steps, replacement)
                raise

        if profile.get("ldap_enabled") and ldap.action not in COMPLETED_LDAP_ACTIONS:
            snapshot = document.get("ldap_snapshot") or {}
            template = snapshot.get("ldif_template") or DEFAULT_LDIF_TEMPLATE
            try:
                ldif_content = render_ldif(
                    template,
                    username=username,
                    password=data.password or "",
                    first_name=inputs.get("first_name"),
                    middle_name=inputs.get("middle_name"),
                    last_name=inputs.get("last_name"),
                    employee_id=inputs.get("employee_id"),
                    base_dn=snapshot.get("base_dn", ""),
                )
                ldap_profile_id = snapshot.get("profile_id") or profile.get("ldap_profile_id")
                ldap_profile = await get_ldap_profile_document(database, ldap_profile_id)
                ldap_write = await add_ldap_entry_from_ldif(ldap_profile, ldif_content)
                ldap = ProvisioningExecutionLdap(
                    enabled=True,
                    action=ldap_write["action"],
                    profile_id=ldap_profile_id,
                    profile_name=snapshot.get("profile_name") or ldap_profile.get("name", "LDAP"),
                    filename=f"{username}.ldif",
                    content=ldif_content,
                    dn=ldap_write["dn"],
                )
            except Exception as exc:
                ldap = ProvisioningExecutionLdap(
                    enabled=True,
                    action="failed",
                    profile_id=snapshot.get("profile_id") or profile.get("ldap_profile_id"),
                    profile_name=snapshot.get("profile_name"),
                    error=_safe_error(exc),
                )
                raise

    except Exception as exc:
        current_error = _safe_error(exc)

    completed_at = datetime.now(timezone.utc)
    succeeded = current_error is None and _all_completed(
        profile, account, roles, steps, ldap, desired_roles
    )
    had_prior_mutation = (
        (document.get("account") or {}).get("action") in {"created", "altered"}
        or any(role.get("action") == "granted" for role in (document.get("roles") or []))
        or any(step.get("action") in {"inserted", "updated"} for step in (document.get("table_steps") or []))
    )
    status = "succeeded" if succeeded else ("partial" if had_prior_mutation or retry_mutated else "failed")

    attempt = ProvisioningRetryAttempt(
        operator_username=operator.username,
        requester_ip=requester_ip,
        status=status,
        started_at=attempt_started,
        completed_at=completed_at,
        error=current_error,
    )
    persisted_ldap = None
    if ldap is not None:
        persisted_ldap = {**ldap.model_dump(mode="python"), "content": None}

    await database.provisioning_runs.update_one(
        {"_id": document["_id"]},
        {
            "$set": {
                "status": status,
                "account": account.model_dump(mode="python") if account else None,
                "roles": [role.model_dump(mode="python") for role in roles],
                "table_steps": [step.model_dump(mode="python") for step in steps],
                "ldap": persisted_ldap,
                "error": current_error,
                "completed_at": completed_at,
                "updated_at": completed_at,
            },
            "$push": {"retry_attempts": attempt.model_dump(mode="python")},
            "$inc": {"retry_count": 1},
        },
    )

    await finish_database_action(
        database,
        audit_id,
        status=(
            DatabaseActionStatus.SUCCEEDED
            if status == "succeeded"
            else DatabaseActionStatus.PARTIAL
            if status == "partial"
            else DatabaseActionStatus.FAILED
        ),
        after={"provisioning_run_id": run_id, "status": status},
        error=current_error,
        details={
            "provisioning_run_id": run_id,
            "password_stored_in_audit": False,
            "completed_steps_skipped": True,
        },
    )

    response_ldap = ldap or ProvisioningExecutionLdap(enabled=False)
    if ldif_content and response_ldap.action in COMPLETED_LDAP_ACTIONS:
        response_ldap.content = ldif_content

    return ProvisioningExecutionResponse(
        run_id=run_id,
        audit_id=audit_id,
        status=status,
        username=username,
        profile_id=document.get("profile_id", ""),
        profile_name=document.get("profile_name", document.get("profile_id", "")),
        schema_connection_id=parent_connection_id,
        schema_connection_name=document.get("parent_connection_name", parent_connection.get("name", parent_connection_id)),
        requester_ip=requester_ip,
        account=account or ProvisioningExecutionAccount(action="failed", error=current_error),
        roles=roles,
        table_steps=steps,
        ldap=response_ldap,
        error=current_error,
    )


def _persisted_values_match(current: dict[str, object], expected: dict[str, object]) -> bool:
    for column, expected_value in expected.items():
        if expected_value == "<redacted>":
            return False
        if _display_value(current.get(column)) != (None if expected_value is None else str(expected_value)):
            return False
    return True


async def build_deprovision_preview(
    database,
    parent_connection_id: str,
    run_id: str,
) -> ProvisioningDeprovisionPreviewResponse:
    document = await _get_run_document(database, parent_connection_id, run_id)
    generated_at = datetime.now(timezone.utc)
    items: list[ProvisioningDeprovisionPreviewItem] = []
    warnings = [
        "Preview only. Phase 4C does not expose DROP USER, REVOKE, DELETE, UPDATE restore, or LDAP delete execution.",
        "Any state changed after provisioning blocks automatic reversal unless DBAChum can prove the row still matches the recorded post-provision state.",
    ]

    parent_connection = await get_database_connection(database, parent_connection_id)
    username = document.get("username", "")
    account = document.get("account") or {}

    if account.get("action") == "created":
        try:
            exists = await oracle_user_exists(parent_connection, username)
        except Exception as exc:
            items.append(ProvisioningDeprovisionPreviewItem(
                component="account",
                label=f"Oracle account {username}",
                planned_action=f"Review DROP USER {username}",
                safe_to_reverse=False,
                state="blocked",
                reason="Live account verification failed: " + _safe_error(exc),
            ))
        else:
            if exists:
                items.append(ProvisioningDeprovisionPreviewItem(
                    component="account",
                    label=f"Oracle account {username}",
                    planned_action=f"Review DROP USER {username}",
                    safe_to_reverse=False,
                    state="candidate",
                    reason="This lifecycle created the account, but a later schema/object/privilege review is required before any drop.",
                ))
            else:
                items.append(ProvisioningDeprovisionPreviewItem(
                    component="account",
                    label=f"Oracle account {username}",
                    planned_action="No action",
                    safe_to_reverse=True,
                    state="already_absent",
                    reason="The lifecycle-created Oracle account is already absent.",
                ))
    else:
        items.append(ProvisioningDeprovisionPreviewItem(
            component="account",
            label=f"Oracle account {username}",
            planned_action="Preserve account",
            safe_to_reverse=True,
            state="no_action",
            reason="The account existed before this lifecycle; Phase 4C will never propose dropping it.",
        ))

    for role in document.get("roles") or []:
        role_name = role.get("name", "")
        if role.get("action") == "granted":
            items.append(ProvisioningDeprovisionPreviewItem(
                component="role",
                label=f"Role {role_name}",
                planned_action=f"Review REVOKE {role_name} FROM {username}",
                safe_to_reverse=False,
                state="candidate",
                reason="DBAChum recorded that this lifecycle granted the role. A live privilege review is still required before revoke.",
            ))
        else:
            items.append(ProvisioningDeprovisionPreviewItem(
                component="role",
                label=f"Role {role_name}",
                planned_action="Preserve role",
                safe_to_reverse=True,
                state="no_action",
                reason="The role was already present before this lifecycle and is not owned by this provisioning run.",
            ))

    profile = document.get("profile_snapshot") or {}
    profile_steps = profile.get("table_steps") or []
    recorded_steps = {int(step.get("index")): step for step in (document.get("table_steps") or []) if step.get("index") is not None}
    inputs = document.get("input_snapshot") or {}
    generated_context = dict(document.get("generated_context") or {})
    generated_context["username"] = username
    generated_context["password"] = None

    for index, profile_step in enumerate(profile_steps, start=1):
        recorded = recorded_steps.get(index)
        if not recorded or recorded.get("action") not in COMPLETED_TABLE_ACTIONS:
            continue

        label = f"Step {index} · {profile_step.get('name', 'Unnamed')} · {profile_step.get('owner')}.{profile_step.get('table_name')}"
        action = recorded.get("action")
        if action == "unchanged":
            items.append(ProvisioningDeprovisionPreviewItem(
                component="table", label=label, planned_action="No action", safe_to_reverse=True,
                state="no_action", reason="This lifecycle did not change the matched application row."
            ))
            continue

        sensitive_columns = set(recorded.get("sensitive_columns") or [])
        if sensitive_columns:
            verb = "DELETE inserted row" if action == "inserted" else "restore previous row values"
            items.append(ProvisioningDeprovisionPreviewItem(
                component="table",
                label=label,
                planned_action=f"Manual review: {verb}",
                safe_to_reverse=False,
                state="blocked",
                reason=(
                    "The row includes redacted password/sensitive column(s): "
                    + ", ".join(sorted(sensitive_columns))
                    + ". DBAChum intentionally did not persist those values, so it cannot prove the full row is unchanged."
                ),
            ))
            continue

        try:
            insert_values, _update_values, _sequence_columns, _ = _resolve_step_values(
                profile_step,
                form_values=inputs,
                generated_values=generated_context,
            )
            match_columns = effective_match_columns(profile_step)
            match_values = {column: insert_values.get(column) for column in match_columns}
            if any(value is None for value in match_values.values()):
                raise AppError(
                    "The original match key cannot be reconstructed without a non-persisted secret.",
                    code="PROVISIONING_DEPROVISION_MATCH_UNAVAILABLE",
                    status_code=409,
                )
            connection = await get_database_connection(database, profile_step["connection_id"])
            expected_after = recorded.get("after_values") or {}
            expected_before = recorded.get("before_values") or {}
            live = await fetch_oracle_provisioning_row(
                connection,
                owner=profile_step["owner"],
                table_name=profile_step["table_name"],
                match_values=match_values,
                columns=list(expected_after.keys()),
            )
        except Exception as exc:
            items.append(ProvisioningDeprovisionPreviewItem(
                component="table", label=label,
                planned_action="Manual review required",
                safe_to_reverse=False, state="blocked",
                reason="Live row verification failed: " + _safe_error(exc),
            ))
            continue

        if live.get("existing_rows") == 0:
            items.append(ProvisioningDeprovisionPreviewItem(
                component="table", label=label, planned_action="No action",
                safe_to_reverse=True, state="already_absent",
                reason="The lifecycle row is already absent."
            ))
            continue
        if live.get("existing_rows") != 1:
            items.append(ProvisioningDeprovisionPreviewItem(
                component="table", label=label, planned_action="Manual review required",
                safe_to_reverse=False, state="blocked",
                reason=f"The match key now identifies {live.get('existing_rows')} rows, so reversal is ambiguous."
            ))
            continue
        if not expected_after or not _persisted_values_match(live.get("values") or {}, expected_after):
            items.append(ProvisioningDeprovisionPreviewItem(
                component="table", label=label, planned_action="Preserve current row",
                safe_to_reverse=False, state="blocked",
                reason="The current row no longer exactly matches the recorded post-provision values; later changes must not be overwritten."
            ))
            continue

        if action == "inserted":
            items.append(ProvisioningDeprovisionPreviewItem(
                component="table", label=label, planned_action="Candidate DELETE of the inserted row",
                safe_to_reverse=True, state="candidate",
                reason="The row was inserted by this lifecycle and still exactly matches the recorded non-sensitive post-provision state."
            ))
        else:
            items.append(ProvisioningDeprovisionPreviewItem(
                component="table", label=label, planned_action="Candidate restore of recorded pre-provision values",
                safe_to_reverse=bool(expected_before), state="candidate" if expected_before else "blocked",
                reason=(
                    "The current row still matches the recorded post-provision state, so the recorded previous values can be reviewed for restore."
                    if expected_before
                    else "No complete pre-provision values were recorded, so automatic restore is blocked."
                ),
            ))

    ldap = document.get("ldap") or {}
    if ldap.get("action") == "generated":
        items.append(ProvisioningDeprovisionPreviewItem(
            component="ldap",
            label=f"LDAP {ldap.get('dn') or username}",
            planned_action="No automatic directory action",
            safe_to_reverse=True,
            state="no_action",
            reason="DBAChum generated an LDIF file only; it did not write the LDAP directory itself.",
        ))

    safe_candidate_count = sum(1 for item in items if item.state == "candidate" and item.safe_to_reverse)
    blocked_count = sum(1 for item in items if item.state == "blocked" or (item.state == "candidate" and not item.safe_to_reverse))
    return ProvisioningDeprovisionPreviewResponse(
        run_id=run_id,
        username=username,
        generated_at=generated_at,
        destructive_execution_enabled=False,
        items=items,
        safe_candidate_count=safe_candidate_count,
        blocked_count=blocked_count,
        warnings=warnings,
    )
