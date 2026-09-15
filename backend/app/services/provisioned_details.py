from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from app.connectors.oracle_provisioning import (
    count_oracle_unique_conflicts,
    fetch_oracle_provisioning_row,
    normalize_oracle_identifier,
    oracle_user_exists,
    update_oracle_provisioning_row,
)
from app.core.exceptions import AppError
from app.schemas.database_action import DatabaseActionRisk, DatabaseActionStatus
from app.schemas.provisioning import (
    OracleProvisionedDetailField,
    OracleProvisionedDetailStep,
    OracleProvisionedDetailsChange,
    OracleProvisionedDetailsEditRequest,
    OracleProvisionedDetailsEditResponse,
    OracleProvisionedDetailsExecutionStep,
    OracleProvisionedDetailsPreviewResponse,
    OracleProvisionedDetailsResponse,
)
from app.schemas.user import UserResponse
from app.services.database_actions import finish_database_action, start_database_action
from app.services.database_connections import get_database_connection
from app.services.ldap_ldif import normalize_employee_id, normalize_person_name
from app.services.provisioning import (
    FORM_SOURCE_OPTIONS,
    list_provisioning_profiles_for_connection,
)


FORM_SOURCE_LABELS = {
    str(item["key"]): str(item["label"])
    for item in FORM_SOURCE_OPTIONS
}

SOURCE_LENGTHS = {
    "first_name": 100,
    "middle_name": 100,
    "last_name": 100,
    "employee_id": 100,
    "reference_user": 30,
    "requestor": 200,
    "request_reference": 100,
    "remarks": 1000,
}


def _profile_dict(profile) -> dict:
    if isinstance(profile, dict):
        return profile
    if hasattr(profile, "model_dump"):
        return profile.model_dump(mode="python")
    raise TypeError("Unsupported provisioning profile.")


def _display_value(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value.rstrip()
    return str(value)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.message
    return str(exc) or exc.__class__.__name__


def _username_mapping(step: dict) -> tuple[dict | None, str | None]:
    matches = [
        mapping
        for mapping in (step.get("mappings") or [])
        if mapping.get("value_kind") == "generated"
        and mapping.get("value_key") == "username"
    ]
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        return None, (
            "Multiple columns map to the generated username. "
            "A single immutable username relationship is required before this table can be edited."
        )
    return None, (
        "No generated username relationship is configured. "
        "This table cannot be edited safely from the DBA_USERS account list."
    )


def _editable_mappings(step: dict) -> list[dict]:
    result: list[dict] = []
    seen: set[str] = set()
    for mapping in step.get("mappings") or []:
        if mapping.get("value_kind") != "form":
            continue
        column = str(mapping.get("column_name") or "").strip().upper()
        source_key = str(mapping.get("value_key") or "").strip()
        if not column or source_key not in FORM_SOURCE_LABELS or column in seen:
            continue
        seen.add(column)
        result.append({**mapping, "column_name": column, "value_key": source_key})
    return result


def _normalize_edit_value(source_key: str, value: str | None) -> str | None:
    if value is None:
        cleaned = None
    else:
        cleaned = value.strip()
        if not cleaned:
            cleaned = None

    if source_key in {"first_name", "middle_name", "last_name"}:
        cleaned = normalize_person_name(cleaned)
    elif source_key == "employee_id":
        cleaned = normalize_employee_id(cleaned)
    elif source_key == "reference_user" and cleaned:
        cleaned = normalize_oracle_identifier(cleaned, field_name="Reference username")

    max_length = SOURCE_LENGTHS.get(source_key, 2000)
    if cleaned is not None and len(cleaned) > max_length:
        label = FORM_SOURCE_LABELS.get(source_key, source_key)
        raise AppError(
            f"{label} cannot exceed {max_length} characters.",
            code="PROVISIONED_DETAILS_VALUE_TOO_LONG",
            status_code=400,
        )
    return cleaned


def _step_key(profile_id: str, step_index: int, column_name: str) -> tuple[str, int, str]:
    return (profile_id, int(step_index), str(column_name).strip().upper())


async def load_oracle_user_provisioned_details(
    database,
    parent_connection_id: str,
    username: str,
) -> OracleProvisionedDetailsResponse:
    username = normalize_oracle_identifier(username, field_name="Username")
    generated_at = datetime.now(timezone.utc)

    parent_connection = await get_database_connection(database, parent_connection_id)
    if parent_connection.get("engine") != "oracle":
        raise AppError(
            "Provisioned detail editing is only available for Oracle database connections.",
            code="PROVISIONED_DETAILS_REQUIRES_ORACLE",
            status_code=400,
        )
    if not await oracle_user_exists(parent_connection, username):
        raise AppError(
            "Oracle user was not found.",
            code="ORACLE_USER_NOT_FOUND",
            status_code=404,
        )

    profiles = await list_provisioning_profiles_for_connection(
        database, parent_connection_id
    )

    steps: list[OracleProvisionedDetailStep] = []
    warnings: list[str] = []
    seen_targets: set[tuple[str, str, str, str]] = set()

    for profile_model in profiles:
        profile = _profile_dict(profile_model)
        profile_id = str(profile.get("id") or profile.get("_id") or "")
        profile_name = str(profile.get("name") or profile_id or "Provisioning profile")
        if profile.get("ready") is False:
            issues = [str(issue) for issue in (profile.get("issues") or [])]
            warnings.append(
                f"{profile_name} was skipped because the provisioning profile is not ready"
                + (": " + "; ".join(issues) if issues else ".")
            )
            continue

        for index, raw_step in enumerate(profile.get("table_steps") or [], start=1):
            step = raw_step if isinstance(raw_step, dict) else raw_step.model_dump(mode="python")
            editable = _editable_mappings(step)
            if not editable:
                continue

            username_mapping, relationship_issue = _username_mapping(step)
            label = (
                f"{profile_name} · Step {index} · "
                f"{step.get('owner')}.{step.get('table_name')}"
            )
            if relationship_issue:
                warnings.append(label + ": " + relationship_issue)
                continue

            username_column = str(username_mapping.get("column_name") or "").strip().upper()
            target_key = (
                str(step.get("connection_id") or ""),
                str(step.get("owner") or "").strip().upper(),
                str(step.get("table_name") or "").strip().upper(),
                username_column,
            )
            if target_key in seen_targets:
                warnings.append(
                    label
                    + ": this table relationship is already represented by another enabled provisioning profile and was skipped to avoid duplicate edits."
                )
                continue
            seen_targets.add(target_key)

            try:
                step_connection = await get_database_connection(
                    database, str(step.get("connection_id") or "")
                )
                live = await fetch_oracle_provisioning_row(
                    step_connection,
                    owner=str(step.get("owner") or ""),
                    table_name=str(step.get("table_name") or ""),
                    match_values={username_column: username},
                    columns=[mapping["column_name"] for mapping in editable],
                )
            except Exception as exc:
                warnings.append(label + ": live row lookup failed: " + _safe_error(exc))
                continue

            existing_rows = int(live.get("existing_rows") or 0)
            if existing_rows == 0:
                continue
            if existing_rows != 1:
                warnings.append(
                    label
                    + f": the immutable username relationship matched {existing_rows} rows, so editing is blocked until the duplicate rows are resolved."
                )
                continue

            values = live.get("values") or {}
            fields = [
                OracleProvisionedDetailField(
                    column_name=mapping["column_name"],
                    source_key=mapping["value_key"],
                    source_label=FORM_SOURCE_LABELS[mapping["value_key"]],
                    value=_display_value(values.get(mapping["column_name"])),
                    strict_unique=bool(mapping.get("strict_unique")),
                )
                for mapping in editable
            ]
            steps.append(
                OracleProvisionedDetailStep(
                    profile_id=profile_id,
                    profile_name=profile_name,
                    step_index=index,
                    step_name=str(step.get("name") or f"Step {index}"),
                    connection_id=str(step.get("connection_id") or ""),
                    connection_name=str(step_connection.get("name") or step.get("connection_id") or ""),
                    owner=str(step.get("owner") or "").strip().upper(),
                    table_name=str(step.get("table_name") or "").strip().upper(),
                    username_column=username_column,
                    username_value=username,
                    fields=fields,
                )
            )

    return OracleProvisionedDetailsResponse(
        username=username,
        generated_at=generated_at,
        steps=steps,
        editable_field_count=sum(len(step.fields) for step in steps),
        warnings=warnings,
    )


async def build_oracle_user_provisioned_details_preview(
    database,
    parent_connection_id: str,
    username: str,
    data: OracleProvisionedDetailsEditRequest,
) -> OracleProvisionedDetailsPreviewResponse:
    state = await load_oracle_user_provisioned_details(
        database, parent_connection_id, username
    )

    available: dict[tuple[str, int, str], tuple[OracleProvisionedDetailStep, OracleProvisionedDetailField]] = {}
    for step in state.steps:
        for field in step.fields:
            available[_step_key(step.profile_id, step.step_index, field.column_name)] = (step, field)

    submitted: dict[tuple[str, int, str], str | None] = {}
    for update in data.updates:
        key = _step_key(update.profile_id, update.step_index, update.column_name)
        if key in submitted:
            raise AppError(
                "The same provisioned column cannot be submitted more than once.",
                code="PROVISIONED_DETAILS_DUPLICATE_UPDATE",
                status_code=400,
            )
        if key not in available:
            raise AppError(
                "A requested provisioned field is no longer editable. Reload the user and try again.",
                code="PROVISIONED_DETAILS_FIELD_NOT_EDITABLE",
                status_code=409,
            )
        submitted[key] = update.value

    changes: list[OracleProvisionedDetailsChange] = []
    blocked_reasons: list[str] = []

    for key, raw_value in submitted.items():
        step, field = available[key]
        after_value = _normalize_edit_value(field.source_key, raw_value)
        before_value = field.value
        if (before_value or None) == (after_value or None):
            continue

        strict_match_count = 0
        strict_conflict = False
        if field.strict_unique:
            if after_value is None:
                strict_conflict = True
                blocked_reasons.append(
                    f"{step.owner}.{step.table_name}.{field.column_name}: strict unique fields cannot be blank."
                )
            else:
                try:
                    step_connection = await get_database_connection(
                        database, step.connection_id
                    )
                    strict_match_count = await count_oracle_unique_conflicts(
                        step_connection,
                        owner=step.owner,
                        table_name=step.table_name,
                        column_name=field.column_name,
                        value=after_value,
                        exclude_match_values={step.username_column: state.username},
                    )
                    strict_conflict = strict_match_count > 0
                    if strict_conflict:
                        blocked_reasons.append(
                            f"{step.owner}.{step.table_name}.{field.column_name}: value {after_value!r} is already used by {strict_match_count} other row(s)."
                        )
                except Exception as exc:
                    strict_conflict = True
                    blocked_reasons.append(
                        f"{step.owner}.{step.table_name}.{field.column_name}: strict uniqueness check failed: {_safe_error(exc)}"
                    )

        changes.append(
            OracleProvisionedDetailsChange(
                profile_id=step.profile_id,
                profile_name=step.profile_name,
                step_index=step.step_index,
                step_name=step.step_name,
                connection_id=step.connection_id,
                connection_name=step.connection_name,
                owner=step.owner,
                table_name=step.table_name,
                username_column=step.username_column,
                column_name=field.column_name,
                source_key=field.source_key,
                source_label=field.source_label,
                before_value=before_value,
                after_value=after_value,
                strict_unique=field.strict_unique,
                strict_match_count=strict_match_count,
                strict_conflict=strict_conflict,
            )
        )

    warnings = list(state.warnings)
    if not changes:
        warnings.append("No provisioned detail changes are pending.")

    return OracleProvisionedDetailsPreviewResponse(
        username=state.username,
        generated_at=datetime.now(timezone.utc),
        ready_to_execute=bool(changes) and not blocked_reasons,
        changes=changes,
        warnings=warnings,
        blocked_reasons=blocked_reasons,
    )


async def execute_oracle_user_provisioned_details_edit(
    database,
    parent_connection_id: str,
    username: str,
    data: OracleProvisionedDetailsEditRequest,
    operator: UserResponse,
) -> OracleProvisionedDetailsEditResponse:
    preview = await build_oracle_user_provisioned_details_preview(
        database, parent_connection_id, username, data
    )
    if not preview.ready_to_execute:
        reason = preview.blocked_reasons[0] if preview.blocked_reasons else "No provisioned detail changes are pending."
        raise AppError(
            "Provisioned detail update is blocked: " + reason,
            code="PROVISIONED_DETAILS_PREVIEW_BLOCKED",
            status_code=409,
        )

    audit_id = await start_database_action(
        database,
        connection_id=parent_connection_id,
        engine="oracle",
        action="edit_provisioned_details",
        target=preview.username,
        operator=operator,
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=(data.request_reference or "").strip() or None,
        before={
            "oracle_username": preview.username,
            "dba_users_username_changed": False,
            "changes": [
                {
                    "profile": change.profile_name,
                    "table": f"{change.owner}.{change.table_name}",
                    "column": change.column_name,
                    "before": change.before_value,
                }
                for change in preview.changes
            ],
        },
        details={
            "username_relationship_locked": True,
            "change_count": len(preview.changes),
        },
    )

    grouped: dict[tuple[str, int], list[OracleProvisionedDetailsChange]] = defaultdict(list)
    for change in preview.changes:
        grouped[(change.profile_id, change.step_index)].append(change)

    results: list[OracleProvisionedDetailsExecutionStep] = []
    applied = 0
    error: str | None = None

    for (_profile_id, _step_index), changes in grouped.items():
        first = changes[0]
        try:
            step_connection = await get_database_connection(database, first.connection_id)

            # Re-check strict values immediately before each write. The immutable username
            # relationship is excluded so the row never conflicts with itself.
            for change in changes:
                if not change.strict_unique or change.after_value is None:
                    continue
                conflicts = await count_oracle_unique_conflicts(
                    step_connection,
                    owner=first.owner,
                    table_name=first.table_name,
                    column_name=change.column_name,
                    value=change.after_value,
                    exclude_match_values={first.username_column: preview.username},
                )
                if conflicts:
                    raise AppError(
                        f"{change.column_name} value {change.after_value!r} is already used by {conflicts} other row(s).",
                        code="PROVISIONED_DETAILS_STRICT_CONFLICT",
                        status_code=409,
                    )

            outcome = await update_oracle_provisioning_row(
                step_connection,
                owner=first.owner,
                table_name=first.table_name,
                match_values={first.username_column: preview.username},
                update_values={change.column_name: change.after_value for change in changes},
            )
            rowcount = int(outcome.get("rowcount") or 0)
            applied += len(changes)
            results.append(
                OracleProvisionedDetailsExecutionStep(
                    profile_id=first.profile_id,
                    profile_name=first.profile_name,
                    step_index=first.step_index,
                    step_name=first.step_name,
                    connection_id=first.connection_id,
                    connection_name=first.connection_name,
                    owner=first.owner,
                    table_name=first.table_name,
                    status="succeeded",
                    affected_rows=rowcount,
                )
            )
        except Exception as exc:
            error = _safe_error(exc)
            results.append(
                OracleProvisionedDetailsExecutionStep(
                    profile_id=first.profile_id,
                    profile_name=first.profile_name,
                    step_index=first.step_index,
                    step_name=first.step_name,
                    connection_id=first.connection_id,
                    connection_name=first.connection_name,
                    owner=first.owner,
                    table_name=first.table_name,
                    status="failed",
                    affected_rows=0,
                    error=error,
                )
            )
            break

    if error is None:
        status = DatabaseActionStatus.SUCCEEDED
    elif applied:
        status = DatabaseActionStatus.PARTIAL
    else:
        status = DatabaseActionStatus.FAILED

    await finish_database_action(
        database,
        audit_id,
        status=status,
        after={
            "oracle_username": preview.username,
            "dba_users_username_changed": False,
            "changes_applied": applied,
            "changes": [
                {
                    "profile": change.profile_name,
                    "table": f"{change.owner}.{change.table_name}",
                    "column": change.column_name,
                    "after": change.after_value,
                }
                for change in preview.changes
                if any(
                    result.profile_id == change.profile_id
                    and result.step_index == change.step_index
                    and result.status == "succeeded"
                    for result in results
                )
            ],
        },
        error=error,
        details={
            "username_relationship_locked": True,
            "execution_steps": [result.model_dump(mode="json") for result in results],
        },
    )

    return OracleProvisionedDetailsEditResponse(
        audit_id=audit_id,
        status=status.value,
        username=preview.username,
        changes_applied=applied,
        steps=results,
        error=error,
    )
