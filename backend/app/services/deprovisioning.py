from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from app.connectors.oracle_provisioning import (
    count_oracle_rows_by_match,
    fetch_oracle_provisioning_row,
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
    OracleUserDeprovisionProfileOption,
    OracleUserDeprovisionRequest,
    OracleUserDeprovisionResponse,
    OracleUserDeprovisionPreviewItem,
    OracleUserDeprovisionPreviewResponse,
)
from app.schemas.user import UserResponse
from app.services.database_actions import finish_database_action, start_database_action
from app.services.database_connections import get_database_connection
from app.services.ldap_directory import delete_ldap_entry, find_ldap_entries_for_username
from app.services.provisioning import effective_match_columns, get_ldap_profile_document
from app.services.provisioning_execution import _display_value, _safe_error


def _is_protected_oracle_user(username: str) -> bool:
    return is_oracle_system_account(username)


def _active_run_query(parent_connection_id: str, username: str) -> dict:
    return {
        "parent_connection_id": parent_connection_id,
        "username": username,
        "status": {"$in": ["succeeded", "partial"]},
        "$or": [
            {"deprovisioned_at": {"$exists": False}},
            {"deprovisioned_at": None},
        ],
    }


async def _active_run_documents(database, parent_connection_id: str, username: str) -> list[dict]:
    cursor = (
        database.provisioning_runs.find(_active_run_query(parent_connection_id, username))
        .sort("started_at", -1)
    )
    return await cursor.to_list(250)


async def list_oracle_user_deprovision_profiles(
    database,
    parent_connection_id: str,
    username: str,
) -> list[OracleUserDeprovisionProfileOption]:
    username = normalize_oracle_identifier(username, field_name="Schema name")
    parent_connection = await get_database_connection(database, parent_connection_id)
    if parent_connection.get("engine") != "oracle":
        raise AppError(
            "Schema deprovisioning is only available for Oracle database connections.",
            code="ORACLE_DEPROVISION_REQUIRES_ORACLE",
            status_code=400,
        )
    documents = await _active_run_documents(database, parent_connection_id, username)

    grouped: dict[str, dict] = {}
    for document in documents:
        profile_id = str(document.get("profile_id") or "").strip()
        if not profile_id:
            continue
        current = grouped.get(profile_id)
        if current is None:
            grouped[profile_id] = {
                "profile_id": profile_id,
                "profile_name": str(document.get("profile_name") or profile_id),
                "last_used_at": document.get("started_at"),
                "run_count": 1,
            }
        else:
            current["run_count"] += 1

    return [OracleUserDeprovisionProfileOption(**value) for value in grouped.values()]


async def _selected_lifecycle_context(
    database,
    parent_connection_id: str,
    username: str,
    profile_id: str,
) -> tuple[int, dict, dict, dict]:
    documents = await _active_run_documents(database, parent_connection_id, username)
    matching = [
        document
        for document in documents
        if str(document.get("profile_id") or "") == profile_id
    ]
    if not matching:
        raise AppError(
            "The selected provisioning profile was not found in this account's active provisioning history.",
            code="ORACLE_DEPROVISION_PROFILE_NOT_USED",
            status_code=404,
        )

    latest = matching[0]
    profile = deepcopy(latest.get("profile_snapshot") or {})
    if not profile:
        raise AppError(
            "The selected provisioning history predates lifecycle snapshots. Use Oracle account only or review this account manually.",
            code="ORACLE_DEPROVISION_PROFILE_SNAPSHOT_MISSING",
            status_code=409,
        )

    profile["id"] = profile_id
    profile["name"] = str(latest.get("profile_name") or profile.get("name") or profile_id)
    inputs = dict(latest.get("input_snapshot") or {})
    if latest.get("employee_id") and not inputs.get("employee_id"):
        inputs["employee_id"] = latest.get("employee_id")
    return len(matching), inputs, profile, latest


def _step_dict(step) -> dict:
    if isinstance(step, dict):
        return step
    if hasattr(step, "model_dump"):
        return step.model_dump(mode="python")
    raise TypeError("Unsupported provisioning table step.")


def _persisted_values_match(current: dict[str, object], expected: dict[str, object]) -> bool:
    for column, expected_value in expected.items():
        if expected_value == "<redacted>":
            return False
        if _display_value(current.get(column)) != (None if expected_value is None else str(expected_value)):
            return False
    return True


def _deprovision_match_values(
    step: dict,
    *,
    username: str,
    lifecycle_inputs: dict,
) -> tuple[dict[str, object] | None, str | None]:
    mappings = {
        str(mapping.get("column_name", "")).strip().upper(): mapping
        for mapping in (step.get("mappings") or [])
        if str(mapping.get("column_name", "")).strip()
    }

    username_columns = [
        column
        for column, mapping in mappings.items()
        if mapping.get("value_kind") == "generated"
        and mapping.get("value_key") == "username"
    ]
    if len(username_columns) == 1:
        return {username_columns[0]: username}, None
    if len(username_columns) > 1:
        # A profile may write the generated username into audit/created-by columns too.
        # Prefer the configured match columns when they identify one of those columns.
        match_columns = effective_match_columns(step)
        username_matches = [column for column in match_columns if column in username_columns]
        if len(username_matches) == 1:
            return {username_matches[0]: username}, None
        return None, (
            "Multiple table columns map to the generated username and the saved profile does not identify one as the row match key."
        )

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
        if kind == "form" and key == "employee_id":
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

    employee_columns = [
        column
        for column, mapping in mappings.items()
        if mapping.get("value_kind") == "form"
        and mapping.get("value_key") == "employee_id"
    ]
    employee_id = lifecycle_inputs.get("employee_id")
    if len(employee_columns) == 1 and employee_id not in (None, ""):
        return {employee_columns[0]: employee_id}, None

    return None, None


async def build_oracle_user_deprovision_preview(
    database,
    parent_connection_id: str,
    username: str,
    *,
    profile_id: str | None = None,
    account_only: bool = False,
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

    profile_options = await list_oracle_user_deprovision_profiles(
        database, parent_connection_id, username
    )
    selected_profile_name: str | None = None
    lifecycle_run_count = 0
    lifecycle_inputs: dict = {}
    profiles: list[dict] = []
    selected_run: dict = {}
    remaining_profile_count = len(profile_options)

    if account_only:
        profile_id = None
    else:
        if not profile_id:
            raise AppError(
                "Select one previously used provisioning profile before building the deprovision preview.",
                code="ORACLE_DEPROVISION_PROFILE_REQUIRED",
                status_code=400,
            )
        lifecycle_run_count, lifecycle_inputs, selected_profile, selected_run = await _selected_lifecycle_context(
            database,
            parent_connection_id,
            username,
            profile_id,
        )
        selected_profile_name = str(selected_profile.get("name") or profile_id)
        profiles = [selected_profile]
        remaining_profile_count = max(len(profile_options) - 1, 0)

    items: list[OracleUserDeprovisionPreviewItem] = []
    warnings: list[str] = [
        "Execution re-checks every selected cleanup target immediately before deletion.",
    ]
    if account_only:
        warnings.append("Oracle account only was selected. No provisioning-table or LDAP records will be inspected or removed.")
    else:
        warnings.append(
            f"Only the saved lifecycle snapshot for provisioning profile {selected_profile_name} is inspected."
        )
        if remaining_profile_count:
            warnings.append(
                f"{remaining_profile_count} other provisioned profile(s) remain active for this Oracle account, so the Oracle schema will be kept."
            )

    blocked_reasons: list[str] = []
    protected = _is_protected_oracle_user(username)
    if protected:
        blocked_reasons.append("This is a protected Oracle/system account and cannot be dropped from DBAChum.")

    try:
        account_state = await get_oracle_user_deprovision_state(parent_connection, username)
    except Exception as exc:
        account_state = {"exists": False, "account_status": None, "owned_object_count": 0}
        blocked_reasons.append("Unable to verify the Oracle account: " + _safe_error(exc))

    account_exists = bool(account_state.get("exists"))
    account_status = account_state.get("account_status")
    owned_object_count = int(account_state.get("owned_object_count") or 0)
    should_drop_account = account_only or (not account_only and remaining_profile_count == 0)
    drop_cascade = should_drop_account and owned_object_count > 0

    if not account_exists:
        if account_only:
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
    elif not should_drop_account:
        items.append(
            OracleUserDeprovisionPreviewItem(
                component="account",
                label=f"Oracle schema {username}",
                planned_action="Keep Oracle schema",
                state="no_action",
                reason=f"{remaining_profile_count} other provisioning profile(s) remain active for this account.",
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
                        else "No other active provisioning profiles remain, so the Oracle account will be removed."
                    )
                ),
            )
        )

    recorded_steps = {
        int(step.get("index")): step
        for step in (selected_run.get("table_steps") or [])
        if step.get("index") is not None
    }

    seen_targets: set[tuple] = set()
    for profile in profiles:
        selected_id = str(profile.get("id") or "")
        profile_name = str(profile.get("name") or selected_id or "Provisioning profile")
        for index, raw_step in enumerate(profile.get("table_steps") or [], start=1):
            step = _step_dict(raw_step)
            recorded = recorded_steps.get(index)
            recorded_action = str((recorded or {}).get("action") or "")
            match_values, match_issue = _deprovision_match_values(
                step,
                username=username,
                lifecycle_inputs=lifecycle_inputs,
            )
            label = f"{profile_name} · Step {index} · {step.get('owner')}.{step.get('table_name')}"

            if recorded_action == "unchanged":
                items.append(
                    OracleUserDeprovisionPreviewItem(
                        component="table",
                        label=label,
                        planned_action="No application row change to reverse",
                        state="no_action",
                        reason="This provisioning profile reused an existing row without changing it.",
                        profile_id=selected_id or None,
                        profile_name=profile_name,
                        step_index=index,
                        connection_id=step.get("connection_id"),
                        owner=step.get("owner"),
                        table_name=step.get("table_name"),
                    )
                )
                continue

            if recorded_action == "updated":
                reason = (
                    "This provisioning profile updated a row that already existed. DBAChum will not delete that shared row automatically because it may belong to another active profile or pre-existing application state."
                )
                blocked_reasons.append(label + ": " + reason)
                items.append(
                    OracleUserDeprovisionPreviewItem(
                        component="table",
                        label=label,
                        planned_action="Manual review required — preserve shared row",
                        state="blocked",
                        reason=reason,
                        profile_id=selected_id or None,
                        profile_name=profile_name,
                        step_index=index,
                        connection_id=step.get("connection_id"),
                        owner=step.get("owner"),
                        table_name=step.get("table_name"),
                    )
                )
                continue

            if match_issue:
                blocked_reasons.append(label + ": " + match_issue)
                items.append(
                    OracleUserDeprovisionPreviewItem(
                        component="table",
                        label=label,
                        planned_action="Manual review required",
                        state="blocked",
                        reason=match_issue,
                        profile_id=selected_id or None,
                        profile_name=profile_name,
                        step_index=index,
                        connection_id=step.get("connection_id"),
                        owner=step.get("owner"),
                        table_name=step.get("table_name"),
                    )
                )
                continue

            if not match_values:
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
                step_connection = await get_database_connection(database, step["connection_id"])
                expected_after = (recorded or {}).get("after_values") or {}
                if recorded_action == "inserted" and expected_after:
                    live = await fetch_oracle_provisioning_row(
                        step_connection,
                        owner=step["owner"],
                        table_name=step["table_name"],
                        match_values=match_values,
                        columns=list(expected_after.keys()),
                    )
                    existing_rows = int(live.get("existing_rows") or 0)
                    if existing_rows == 1 and not _persisted_values_match(
                        live.get("values") or {}, expected_after
                    ):
                        reason = (
                            "The row no longer matches the values recorded when this profile inserted it. A later profile or manual change may now depend on the row, so automatic deletion is blocked."
                        )
                        blocked_reasons.append(label + ": " + reason)
                        items.append(
                            OracleUserDeprovisionPreviewItem(
                                component="table",
                                label=label,
                                planned_action="Manual review required — preserve changed row",
                                state="blocked",
                                reason=reason,
                                profile_id=selected_id or None,
                                profile_name=profile_name,
                                step_index=index,
                                connection_id=step.get("connection_id"),
                                owner=step.get("owner"),
                                table_name=step.get("table_name"),
                                match_values={k: None if v is None else str(v) for k, v in match_values.items()},
                                existing_rows=existing_rows,
                            )
                        )
                        continue
                else:
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
                        profile_id=selected_id or None,
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
                profile_id=selected_id or None,
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
                        reason="No row matched this account in the selected provisioning profile.",
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
                        reason="Exactly one row matches the account identity from the selected saved provisioning profile.",
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

    for profile in profiles:
        if not profile.get("ldap_enabled"):
            continue
        ldap_profile_id = str(profile.get("ldap_profile_id") or "")
        if not ldap_profile_id:
            continue
        selected_id = str(profile.get("id") or "")
        profile_name = str(profile.get("name") or selected_id or "Provisioning profile")
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
                    profile_id=selected_id or None,
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
                    reason="No LDAP entry matched this username for the selected provisioning profile.",
                    profile_id=selected_id or None,
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
                    profile_id=selected_id or None,
                    profile_name=profile_name,
                    ldap_profile_id=ldap_profile_id,
                    ldap_dn=matches[0],
                )
            )
        else:
            reason = f"LDAP lookup matched {len(matches)} entries. DBAChum will not guess which directory entry to delete."
            blocked_reasons.append(label + ": " + reason)
            items.append(
                OracleUserDeprovisionPreviewItem(
                    component="ldap",
                    label=label,
                    planned_action="Manual review required",
                    state="blocked",
                    reason=reason,
                    profile_id=selected_id or None,
                    profile_name=profile_name,
                    ldap_profile_id=ldap_profile_id,
                )
            )

    if lifecycle_run_count:
        items.append(
            OracleUserDeprovisionPreviewItem(
                component="history",
                label=f"{selected_profile_name} provisioning history",
                planned_action="Preserve audit history",
                state="no_action",
                reason=f"{lifecycle_run_count} lifecycle run(s) for the selected profile are retained and marked deprovisioned after successful execution.",
                profile_id=profile_id,
                profile_name=selected_profile_name,
            )
        )

    linked_row_count = sum(
        item.existing_rows
        for item in items
        if item.component == "table" and item.state == "candidate"
    )
    linked_ldap_count = sum(
        1 for item in items if item.component == "ldap" and item.state == "candidate"
    )
    blocked_count = sum(1 for item in items if item.state == "blocked")

    account_requirement_ok = account_exists or (not should_drop_account and not account_exists)
    execution_ready = account_requirement_ok and not protected and blocked_count == 0 and not blocked_reasons
    if account_only and not account_exists:
        execution_ready = False

    return OracleUserDeprovisionPreviewResponse(
        username=username,
        generated_at=generated_at,
        selected_profile_id=profile_id,
        selected_profile_name=selected_profile_name,
        account_only=account_only,
        remaining_profile_count=remaining_profile_count,
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
        database,
        parent_connection_id,
        username,
        profile_id=data.profile_id,
        account_only=data.account_only,
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
            "selected_profile_id": preview.selected_profile_id,
            "selected_profile_name": preview.selected_profile_name,
            "account_only": preview.account_only,
            "remaining_profile_count": preview.remaining_profile_count,
        },
        details={
            "confirmation_required": username,
            "selected_profile_id": preview.selected_profile_id,
            "selected_profile_name": preview.selected_profile_name,
            "account_only": preview.account_only,
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

    async def fail(error: str) -> OracleUserDeprovisionResponse:
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

    for item in preview.items:
        if item.component != "table" or item.state != "candidate":
            continue
        try:
            step_connection = await get_database_connection(database, item.connection_id)
            existing_rows = await count_oracle_rows_by_match(
                step_connection,
                owner=item.owner,
                table_name=item.table_name,
                match_values=item.match_values,
            )
            if existing_rows != 1:
                raise AppError(
                    f"Linked row re-check returned {existing_rows} rows instead of exactly one.",
                    code="ORACLE_DEPROVISION_TARGET_CHANGED",
                    status_code=409,
                )
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
            return await fail(error)

    for item in preview.items:
        if item.component != "ldap" or item.state != "candidate":
            continue
        try:
            ldap_profile = await get_ldap_profile_document(database, item.ldap_profile_id or "")
            matches = await find_ldap_entries_for_username(ldap_profile, username)
            if matches != [item.ldap_dn]:
                raise AppError(
                    "LDAP entry re-check no longer matches the reviewed target.",
                    code="ORACLE_DEPROVISION_LDAP_TARGET_CHANGED",
                    status_code=409,
                )
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
            return await fail(error)

    account_item = next(
        (item for item in preview.items if item.component == "account"),
        None,
    )
    if account_item and account_item.state == "candidate":
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
            return await fail(error)

    if preview.selected_profile_id and not preview.account_only:
        now = datetime.now(timezone.utc)
        await database.provisioning_runs.update_many(
            {
                **_active_run_query(parent_connection_id, username),
                "profile_id": preview.selected_profile_id,
            },
            {
                "$set": {
                    "deprovisioned_at": now,
                    "deprovisioned_by": operator.username,
                    "deprovision_audit_id": audit_id,
                }
            },
        )

    await finish_database_action(
        database,
        audit_id,
        status=DatabaseActionStatus.SUCCEEDED,
        after={
            "account_dropped": account_dropped,
            "deleted_provisioning_rows": deleted_rows,
            "deleted_ldap_entries": deleted_ldap_entries,
            "selected_profile_id": preview.selected_profile_id,
            "remaining_profile_count": preview.remaining_profile_count,
        },
        details={"execution_items": [entry.model_dump(mode="json") for entry in execution_items]},
    )
    return OracleUserDeprovisionResponse(
        audit_id=audit_id,
        status="succeeded",
        username=username,
        account_dropped=account_dropped,
        deleted_provisioning_rows=deleted_rows,
        deleted_ldap_entries=deleted_ldap_entries,
        items=execution_items,
        error=None,
    )
