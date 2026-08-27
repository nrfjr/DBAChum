from __future__ import annotations

from datetime import datetime, timezone

from app.connectors.oracle_provisioning import (
    count_oracle_rows_by_match,
    delete_oracle_provisioning_row,
    drop_oracle_user,
    get_oracle_user_deprovision_state,
    normalize_oracle_identifier,
)
from app.core.exceptions import AppError
from app.core.oracle_accounts import is_oracle_system_account
from app.schemas.database_action import DatabaseActionRisk, DatabaseActionStatus
from app.schemas.provisioning import (
    OracleUserDeprovisionExecutionItem,
    OracleUserDeprovisionRequest,
    OracleUserDeprovisionResponse,
    OracleUserDeprovisionPreviewItem,
    OracleUserDeprovisionPreviewResponse,
)
from app.schemas.user import UserResponse
from app.services.database_actions import finish_database_action, start_database_action
from app.services.database_connections import get_database_connection
from app.services.ldap_directory import delete_ldap_entry, find_ldap_entries_for_username
from app.services.provisioning import (
    effective_match_columns,
    get_ldap_profile_document,
    list_provisioning_profiles_for_connection,
)
from app.services.provisioning_execution import _safe_error


def _is_protected_oracle_user(username: str) -> bool:
    return is_oracle_system_account(username)


async def _lifecycle_context(database, parent_connection_id: str, username: str) -> tuple[int, dict]:
    """Return run count and a non-secret identity context for generic cleanup.

    Deprovision does not require a lifecycle run. When one exists, its persisted
    non-secret identity fields can help identify legacy table steps that use an
    employee ID instead of the Oracle username.
    """
    cursor = (
        database.provisioning_runs.find(
            {
                "parent_connection_id": parent_connection_id,
                "username": username,
            }
        )
        .sort("started_at", -1)
    )
    documents = await cursor.to_list(100)
    if not documents:
        return 0, {}

    latest = documents[0]
    inputs = dict(latest.get("input_snapshot") or {})
    if latest.get("employee_id") and not inputs.get("employee_id"):
        inputs["employee_id"] = latest.get("employee_id")
    return len(documents), inputs


def _step_dict(step) -> dict:
    if isinstance(step, dict):
        return step
    if hasattr(step, "model_dump"):
        return step.model_dump(mode="python")
    raise TypeError("Unsupported provisioning table step.")


def _profile_dict(profile) -> dict:
    if isinstance(profile, dict):
        return profile
    if hasattr(profile, "model_dump"):
        return profile.model_dump(mode="python")
    raise TypeError("Unsupported provisioning profile.")


def _deprovision_match_values(
    step: dict,
    *,
    username: str,
    lifecycle_inputs: dict,
) -> tuple[dict[str, object] | None, str | None]:
    """Build a user-specific lookup from the provisioning mapping itself.

    Prefer the configured upsert identity when it contains the generated
    username. This keeps fixed literals (for example an application code) in
    the key. For older profiles whose match key is not username-based, a single
    generated-username mapping can still safely identify the row. Employee ID
    is a fallback only when lifecycle history provides it.
    """
    mappings = {
        str(mapping.get("column_name", "")).strip().upper(): mapping
        for mapping in (step.get("mappings") or [])
        if str(mapping.get("column_name", "")).strip()
    }
    match_columns = effective_match_columns(step)

    configured_values: dict[str, object] = {}
    configured_has_identity = False
    configured_resolvable = bool(match_columns)
    for column in match_columns:
        mapping = mappings.get(column)
        if not mapping:
            configured_resolvable = False
            break
        kind = mapping.get("value_kind")
        key = mapping.get("value_key")
        if kind == "generated" and key == "username":
            configured_values[column] = username
            configured_has_identity = True
        elif kind == "form" and key == "employee_id":
            employee_id = lifecycle_inputs.get("employee_id")
            if employee_id in (None, ""):
                configured_resolvable = False
                break
            configured_values[column] = employee_id
            configured_has_identity = True
        elif kind == "custom":
            configured_values[column] = mapping.get("custom_value")
        else:
            configured_resolvable = False
            break

    if configured_resolvable and configured_has_identity:
        return configured_values, None

    username_columns = [
        column
        for column, mapping in mappings.items()
        if mapping.get("value_kind") == "generated"
        and mapping.get("value_key") == "username"
    ]
    if len(username_columns) == 1:
        return {username_columns[0]: username}, None
    if len(username_columns) > 1:
        return None, (
            "Multiple table columns map to the generated username and the configured match key "
            "does not identify which one is the row identity. Review the provisioning profile."
        )

    employee_columns = [
        column
        for column, mapping in mappings.items()
        if mapping.get("value_kind") == "form"
        and mapping.get("value_key") == "employee_id"
    ]
    employee_id = lifecycle_inputs.get("employee_id")
    if len(employee_columns) == 1 and employee_id not in (None, ""):
        return {employee_columns[0]: employee_id}, None

    # A provisioning table without a username (or known employee ID) mapping
    # is not provably tied to this Oracle account, so it is intentionally not
    # treated as a deprovision target.
    return None, None


async def build_oracle_user_deprovision_preview(
    database,
    parent_connection_id: str,
    username: str,
) -> OracleUserDeprovisionPreviewResponse:
    username = normalize_oracle_identifier(username, field_name="Schema name")
    generated_at = datetime.now(timezone.utc)
    parent_connection = await get_database_connection(database, parent_connection_id)
    if parent_connection.get("engine") != "oracle":
        raise AppError(
            "Schema deprovisioning is only available for Oracle database connections.",
            code="ORACLE_DEPROVISION_REQUIRES_ORACLE",
            status_code=400,
        )

    lifecycle_run_count, lifecycle_inputs = await _lifecycle_context(
        database, parent_connection_id, username
    )

    items: list[OracleUserDeprovisionPreviewItem] = []
    warnings: list[str] = [
        "Execution re-checks every linked cleanup target immediately before deletion.",
        "Only enabled provisioning profiles attached to this parent database are inspected.",
    ]
    blocked_reasons: list[str] = []

    protected = _is_protected_oracle_user(username)
    if protected:
        blocked_reasons.append("This is a protected Oracle/system account and cannot be dropped from DBAChum.")

    try:
        account_state = await get_oracle_user_deprovision_state(parent_connection, username)
    except Exception as exc:
        account_state = {
            "exists": False,
            "account_status": None,
            "owned_object_count": 0,
        }
        blocked_reasons.append("Unable to verify the Oracle account: " + _safe_error(exc))

    account_exists = bool(account_state.get("exists"))
    account_status = account_state.get("account_status")
    owned_object_count = int(account_state.get("owned_object_count") or 0)
    drop_cascade = owned_object_count > 0

    if not account_exists:
        blocked_reasons.append("The Oracle schema/user no longer exists.")
        items.append(
            OracleUserDeprovisionPreviewItem(
                component="account",
                label=f"Oracle schema {username}",
                planned_action="No DROP USER action",
                state="already_absent",
                reason="The Oracle account was not found during the live preview.",
            )
        )
    else:
        drop_sql = f"DROP USER {username}" + (" CASCADE" if drop_cascade else "")
        items.append(
            OracleUserDeprovisionPreviewItem(
                component="account",
                label=f"Oracle schema {username}",
                planned_action=drop_sql,
                state="blocked" if protected else "candidate",
                reason=(
                    "Protected Oracle/system account. DBAChum will not execute this drop."
                    if protected
                    else (
                        f"The schema currently owns {owned_object_count} object(s); DROP USER CASCADE is required and will permanently remove them."
                        if drop_cascade
                        else "The schema owns no objects, so a normal DROP USER is sufficient."
                    )
                ),
            )
        )

    try:
        profiles = await list_provisioning_profiles_for_connection(
            database, parent_connection_id
        )
    except Exception as exc:
        profiles = []
        reason = "Unable to load enabled provisioning profiles: " + _safe_error(exc)
        blocked_reasons.append(reason)
        items.append(
            OracleUserDeprovisionPreviewItem(
                component="table",
                label="Provisioning-table discovery",
                planned_action="Manual review required",
                state="blocked",
                reason=reason,
            )
        )

    seen_targets: set[tuple] = set()
    for profile_model in profiles:
        profile = _profile_dict(profile_model)
        profile_id = str(profile.get("id") or profile.get("_id") or "")
        profile_name = str(profile.get("name") or profile_id or "Provisioning profile")
        for index, raw_step in enumerate(profile.get("table_steps") or [], start=1):
            step = _step_dict(raw_step)
            match_values, match_issue = _deprovision_match_values(
                step,
                username=username,
                lifecycle_inputs=lifecycle_inputs,
            )
            label = (
                f"{profile_name} · Step {index} · "
                f"{step.get('owner')}.{step.get('table_name')}"
            )

            if match_issue:
                blocked_reasons.append(label + ": " + match_issue)
                items.append(
                    OracleUserDeprovisionPreviewItem(
                        component="table",
                        label=label,
                        planned_action="Manual review required",
                        state="blocked",
                        reason=match_issue,
                        profile_id=profile_id or None,
                        profile_name=profile_name,
                        step_index=index,
                        connection_id=step.get("connection_id"),
                        owner=step.get("owner"),
                        table_name=step.get("table_name"),
                    )
                )
                continue

            if not match_values:
                # This profile step does not persist a reconstructible account
                # identity and therefore is not considered linked cleanup.
                continue

            key = (
                step.get("connection_id"),
                step.get("owner"),
                step.get("table_name"),
                tuple(sorted((str(k), str(v)) for k, v in match_values.items())),
            )
            if key in seen_targets:
                continue
            seen_targets.add(key)

            try:
                step_connection = await get_database_connection(
                    database, step["connection_id"]
                )
                existing_rows = await count_oracle_rows_by_match(
                    step_connection,
                    owner=step["owner"],
                    table_name=step["table_name"],
                    match_values=match_values,
                )
            except Exception as exc:
                reason = "Live provisioning-table check failed: " + _safe_error(exc)
                blocked_reasons.append(label + ": " + reason)
                items.append(
                    OracleUserDeprovisionPreviewItem(
                        component="table",
                        label=label,
                        planned_action="Manual review required",
                        state="blocked",
                        reason=reason,
                        profile_id=profile_id or None,
                        profile_name=profile_name,
                        step_index=index,
                        connection_id=step.get("connection_id"),
                        owner=step.get("owner"),
                        table_name=step.get("table_name"),
                        match_values={k: None if v is None else str(v) for k, v in match_values.items()},
                    )
                )
                continue

            common = dict(
                profile_id=profile_id or None,
                profile_name=profile_name,
                step_index=index,
                connection_id=step.get("connection_id"),
                owner=step.get("owner"),
                table_name=step.get("table_name"),
                match_values={k: None if v is None else str(v) for k, v in match_values.items()},
                existing_rows=existing_rows,
            )
            if existing_rows == 0:
                items.append(
                    OracleUserDeprovisionPreviewItem(
                        component="table",
                        label=label,
                        planned_action="No linked row to delete",
                        state="already_absent",
                        reason="No row matched this account in the enabled provisioning table.",
                        **common,
                    )
                )
            elif existing_rows == 1:
                items.append(
                    OracleUserDeprovisionPreviewItem(
                        component="table",
                        label=label,
                        planned_action="DELETE linked provisioning row",
                        state="candidate",
                        reason="Exactly one row matches the account identity defined by this enabled provisioning profile.",
                        **common,
                    )
                )
            else:
                reason = (
                    f"The account identity matches {existing_rows} rows. DBAChum will not bulk-delete an ambiguous provisioning-table match."
                )
                blocked_reasons.append(label + ": " + reason)
                items.append(
                    OracleUserDeprovisionPreviewItem(
                        component="table",
                        label=label,
                        planned_action="Manual review required",
                        state="blocked",
                        reason=reason,
                        **common,
                    )
                )

    seen_ldap_profiles: set[str] = set()
    for profile_model in profiles:
        profile = _profile_dict(profile_model)
        if not profile.get("ldap_enabled"):
            continue
        ldap_profile_id = str(profile.get("ldap_profile_id") or "")
        if not ldap_profile_id or ldap_profile_id in seen_ldap_profiles:
            continue
        seen_ldap_profiles.add(ldap_profile_id)
        profile_id = str(profile.get("id") or profile.get("_id") or "")
        profile_name = str(profile.get("name") or profile_id or "Provisioning profile")
        label = f"{profile_name} · LDAP entry"
        try:
            ldap_profile = await get_ldap_profile_document(database, ldap_profile_id)
            matches = await find_ldap_entries_for_username(ldap_profile, username)
        except Exception as exc:
            reason = "Live LDAP check failed: " + _safe_error(exc)
            blocked_reasons.append(label + ": " + reason)
            items.append(
                OracleUserDeprovisionPreviewItem(
                    component="ldap",
                    label=label,
                    planned_action="Manual review required",
                    state="blocked",
                    reason=reason,
                    profile_id=profile_id or None,
                    profile_name=profile_name,
                    ldap_profile_id=ldap_profile_id,
                )
            )
            continue

        if len(matches) == 0:
            items.append(
                OracleUserDeprovisionPreviewItem(
                    component="ldap",
                    label=label,
                    planned_action="No LDAP entry to delete",
                    state="already_absent",
                    reason="No LDAP entry matched this username in the enabled LDAP profile.",
                    profile_id=profile_id or None,
                    profile_name=profile_name,
                    ldap_profile_id=ldap_profile_id,
                )
            )
        elif len(matches) == 1:
            items.append(
                OracleUserDeprovisionPreviewItem(
                    component="ldap",
                    label=label,
                    planned_action="DELETE LDAP entry",
                    state="candidate",
                    reason="Exactly one LDAP entry matched this username.",
                    profile_id=profile_id or None,
                    profile_name=profile_name,
                    ldap_profile_id=ldap_profile_id,
                    ldap_dn=matches[0],
                )
            )
        else:
            reason = (
                f"LDAP lookup matched {len(matches)} entries. DBAChum will not guess which directory entry to delete."
            )
            blocked_reasons.append(label + ": " + reason)
            items.append(
                OracleUserDeprovisionPreviewItem(
                    component="ldap",
                    label=label,
                    planned_action="Manual review required",
                    state="blocked",
                    reason=reason,
                    profile_id=profile_id or None,
                    profile_name=profile_name,
                    ldap_profile_id=ldap_profile_id,
                )
            )

    if lifecycle_run_count:
        items.append(
            OracleUserDeprovisionPreviewItem(
                component="history",
                label="DBAChum provisioning history",
                planned_action="Preserve audit history",
                state="no_action",
                reason=f"{lifecycle_run_count} lifecycle run(s) were found. History is retained after deprovisioning.",
            )
        )

    linked_row_count = sum(
        item.existing_rows
        for item in items
        if item.component == "table" and item.state == "candidate"
    )
    linked_ldap_count = sum(1 for item in items if item.component == "ldap" and item.state == "candidate")
    blocked_count = sum(1 for item in items if item.state == "blocked")
    execution_ready = account_exists and not protected and blocked_count == 0 and not blocked_reasons

    return OracleUserDeprovisionPreviewResponse(
        username=username,
        generated_at=generated_at,
        account_exists=account_exists,
        account_status=account_status,
        protected_account=protected,
        owned_object_count=owned_object_count,
        drop_cascade=drop_cascade,
        lifecycle_run_count=lifecycle_run_count,
        linked_row_count=linked_row_count,
        linked_ldap_count=linked_ldap_count,
        blocked_count=blocked_count,
        execution_ready=execution_ready,
        confirmation_text=username,
        items=items,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
    )


async def execute_oracle_user_deprovision(
    database,
    parent_connection_id: str,
    username: str,
    data: OracleUserDeprovisionRequest,
    operator: UserResponse,
) -> OracleUserDeprovisionResponse:
    username = normalize_oracle_identifier(username, field_name="Schema name")
    if data.confirmation.strip() != username:
        raise AppError(
            f'Type the exact schema name "{username}" to confirm deprovisioning.',
            code="ORACLE_DEPROVISION_CONFIRMATION_MISMATCH",
            status_code=409,
        )

    preview = await build_oracle_user_deprovision_preview(
        database, parent_connection_id, username
    )
    if not preview.execution_ready:
        reason = preview.blocked_reasons[0] if preview.blocked_reasons else "The current preview is not safe to execute."
        raise AppError(
            "Deprovisioning is blocked: " + reason,
            code="ORACLE_DEPROVISION_PREVIEW_BLOCKED",
            status_code=409,
        )

    parent_connection = await get_database_connection(database, parent_connection_id)
    audit_id = await start_database_action(
        database,
        connection_id=parent_connection_id,
        engine="oracle",
        action="deprovision_oracle_user",
        operator=operator,
        target=username,
        risk=DatabaseActionRisk.DANGEROUS,
        request_reference=data.request_reference,
        before={
            "account_exists": preview.account_exists,
            "account_status": preview.account_status,
            "owned_object_count": preview.owned_object_count,
            "drop_cascade": preview.drop_cascade,
            "lifecycle_run_count": preview.lifecycle_run_count,
            "linked_row_count": preview.linked_row_count,
            "linked_ldap_count": preview.linked_ldap_count,
        },
        details={
            "confirmation_required": username,
            "linked_targets": [
                {
                    "profile_name": item.profile_name,
                    "connection_id": item.connection_id,
                    "owner": item.owner,
                    "table_name": item.table_name,
                    "match_values": item.match_values,
                }
                for item in preview.items
                if item.component == "table" and item.state == "candidate"
            ],
            "ldap_targets": [
                {
                    "profile_name": item.profile_name,
                    "profile_id": item.profile_id,
                    "ldap_profile_id": item.ldap_profile_id,
                    "dn": item.ldap_dn,
                }
                for item in preview.items
                if item.component == "ldap" and item.state == "candidate"
            ],
        },
    )

    execution_items: list[OracleUserDeprovisionExecutionItem] = []
    deleted_rows = 0
    deleted_ldap_entries = 0
    account_dropped = False

    # Delete linked provisioning rows first. If any one fails, stop before the
    # Oracle DROP USER. A retry can safely re-preview already-removed rows.
    for item in preview.items:
        if item.component != "table" or item.state != "candidate":
            continue
        try:
            step_connection = await get_database_connection(database, item.connection_id)
            rowcount = await delete_oracle_provisioning_row(
                step_connection,
                owner=item.owner,
                table_name=item.table_name,
                match_values=item.match_values,
            )
            deleted_rows += rowcount
            execution_items.append(
                OracleUserDeprovisionExecutionItem(
                    component="table",
                    label=item.label,
                    status="succeeded",
                    affected_rows=rowcount,
                )
            )
        except Exception as exc:
            error = _safe_error(exc)
            execution_items.append(
                OracleUserDeprovisionExecutionItem(
                    component="table",
                    label=item.label,
                    status="failed",
                    affected_rows=0,
                    error=error,
                )
            )
            status = DatabaseActionStatus.PARTIAL if deleted_rows else DatabaseActionStatus.FAILED
            await finish_database_action(
                database,
                audit_id,
                status=status,
                after={
                    "account_dropped": False,
                    "deleted_provisioning_rows": deleted_rows,
                    "deleted_ldap_entries": deleted_ldap_entries,
                },
                error=error,
                details={"execution_items": [entry.model_dump(mode="json") for entry in execution_items]},
            )
            return OracleUserDeprovisionResponse(
                audit_id=audit_id,
                status=status.value,
                username=username,
                account_dropped=False,
                deleted_provisioning_rows=deleted_rows,
                deleted_ldap_entries=deleted_ldap_entries,
                items=execution_items,
                error=error,
            )

    # Remove unambiguous LDAP entries only when LDAP is enabled by an active
    # provisioning profile. Any failure stops before the Oracle account drop.
    for item in preview.items:
        if item.component != "ldap" or item.state != "candidate":
            continue
        try:
            ldap_profile = await get_ldap_profile_document(database, item.ldap_profile_id or "")
            removed = await delete_ldap_entry(ldap_profile, item.ldap_dn or "")
            if removed:
                deleted_ldap_entries += 1
            execution_items.append(
                OracleUserDeprovisionExecutionItem(
                    component="ldap",
                    label=item.label,
                    status="succeeded",
                    affected_rows=1 if removed else 0,
                )
            )
        except Exception as exc:
            error = _safe_error(exc)
            execution_items.append(
                OracleUserDeprovisionExecutionItem(
                    component="ldap",
                    label=item.label,
                    status="failed",
                    affected_rows=0,
                    error=error,
                )
            )
            status = DatabaseActionStatus.PARTIAL if (deleted_rows or deleted_ldap_entries) else DatabaseActionStatus.FAILED
            await finish_database_action(
                database,
                audit_id,
                status=status,
                after={
                    "account_dropped": False,
                    "deleted_provisioning_rows": deleted_rows,
                    "deleted_ldap_entries": deleted_ldap_entries,
                },
                error=error,
                details={"execution_items": [entry.model_dump(mode="json") for entry in execution_items]},
            )
            return OracleUserDeprovisionResponse(
                audit_id=audit_id,
                status=status.value,
                username=username,
                account_dropped=False,
                deleted_provisioning_rows=deleted_rows,
                deleted_ldap_entries=deleted_ldap_entries,
                items=execution_items,
                error=error,
            )

    try:
        await drop_oracle_user(
            parent_connection,
            username,
            cascade=preview.drop_cascade,
        )
        account_dropped = True
        execution_items.append(
            OracleUserDeprovisionExecutionItem(
                component="account",
                label=f"Oracle schema {username}",
                status="succeeded",
                affected_rows=1,
            )
        )
    except Exception as exc:
        error = _safe_error(exc)
        execution_items.append(
            OracleUserDeprovisionExecutionItem(
                component="account",
                label=f"Oracle schema {username}",
                status="failed",
                affected_rows=0,
                error=error,
            )
        )
        status = DatabaseActionStatus.PARTIAL if (deleted_rows or deleted_ldap_entries) else DatabaseActionStatus.FAILED
        await finish_database_action(
            database,
            audit_id,
            status=status,
            after={
                "account_dropped": False,
                "deleted_provisioning_rows": deleted_rows,
                "deleted_ldap_entries": deleted_ldap_entries,
            },
            error=error,
            details={"execution_items": [entry.model_dump(mode="json") for entry in execution_items]},
        )
        return OracleUserDeprovisionResponse(
            audit_id=audit_id,
            status=status.value,
            username=username,
            account_dropped=False,
            deleted_provisioning_rows=deleted_rows,
            deleted_ldap_entries=deleted_ldap_entries,
            items=execution_items,
            error=error,
        )

    await finish_database_action(
        database,
        audit_id,
        status=DatabaseActionStatus.SUCCEEDED,
        after={
            "account_dropped": account_dropped,
            "deleted_provisioning_rows": deleted_rows,
            "deleted_ldap_entries": deleted_ldap_entries,
        },
        details={"execution_items": [entry.model_dump(mode="json") for entry in execution_items]},
    )
    return OracleUserDeprovisionResponse(
        audit_id=audit_id,
        status="succeeded",
        username=username,
        account_dropped=True,
        deleted_provisioning_rows=deleted_rows,
        deleted_ldap_entries=deleted_ldap_entries,
        items=execution_items,
        error=None,
    )
