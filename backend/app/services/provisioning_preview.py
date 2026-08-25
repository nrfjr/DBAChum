from __future__ import annotations

from datetime import datetime, timezone

from app.connectors.oracle_provisioning import (
    count_oracle_rows_by_match,
    get_oracle_reference_user,
    is_sensitive_reference_role,
    normalize_oracle_identifier,
    oracle_user_exists,
)
from app.core.exceptions import AppError
from app.schemas.provisioning import (
    ProvisioningPreviewColumn,
    ProvisioningPreviewLdap,
    ProvisioningPreviewRequest,
    ProvisioningPreviewResponse,
    ProvisioningPreviewRole,
    ProvisioningPreviewTableStep,
)
from app.schemas.user import UserResponse
from app.services.database_connections import (
    connection_is_active,
    get_database_connection,
)
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
    validate_profile_dependencies,
)


def generate_provisioning_username(
    *,
    first_name: str | None,
    middle_name: str | None,
    last_name: str | None,
    employee_id: str | None,
) -> str:
    first = (normalize_person_name(first_name) or "").replace(" ", "")
    middle = (normalize_person_name(middle_name) or "").replace(" ", "")
    last = (normalize_person_name(last_name) or "").replace(" ", "")
    employee = normalize_employee_id(employee_id) or ""

    if not first or not last or not employee:
        raise AppError(
            "First name, last name and employee ID are required to generate a username.",
            code="PROVISIONING_USERNAME_FIELDS_REQUIRED",
            status_code=400,
        )

    generated = (
        first[0]
        + (middle[0] if middle else "")
        + last
        + employee
    ).upper()

    return normalize_oracle_identifier(generated, field_name="Generated username")


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


async def build_provisioning_preview(
    database,
    profile_id: str,
    data: ProvisioningPreviewRequest,
    operator: UserResponse,
    requester_ip: str | None = None,
    parent_connection_id: str | None = None,
) -> ProvisioningPreviewResponse:
    profile = await get_provisioning_profile(database, profile_id)

    if not profile.get("enabled", True):
        raise AppError(
            "This provisioning profile is disabled.",
            code="PROVISIONING_PROFILE_DISABLED",
            status_code=400,
        )

    if (
        parent_connection_id is not None
        and profile.get("schema_connection_id") != parent_connection_id
    ):
        raise AppError(
            "This provisioning profile does not belong to the current database connection.",
            code="PROVISIONING_PROFILE_WRONG_DATABASE",
            status_code=400,
        )

    issues = await validate_profile_dependencies(database, profile)
    if issues:
        raise AppError(
            "Provisioning profile is not ready: " + " ".join(issues),
            code="PROVISIONING_PROFILE_NOT_READY",
            status_code=400,
        )

    schema_connection = await get_database_connection(
        database, profile["schema_connection_id"]
    )
    if not connection_is_active(schema_connection):
        raise AppError(
            "Parent database connection is disabled.",
            code="CONNECTION_DISABLED",
            status_code=400,
        )

    first_name = normalize_person_name(data.first_name)
    middle_name = normalize_person_name(data.middle_name)
    last_name = normalize_person_name(data.last_name)
    employee_id = normalize_employee_id(data.employee_id)

    if data.username and data.username.strip():
        username = normalize_oracle_identifier(
            data.username,
            field_name="Username",
        )
    else:
        username = generate_provisioning_username(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            employee_id=employee_id,
        )

    account_exists = await oracle_user_exists(schema_connection, username)

    reference_username = _clean_optional(data.reference_user)
    reference = None
    preview_roles: list[ProvisioningPreviewRole] = []
    warnings: list[str] = []

    if reference_username:
        reference_username = normalize_oracle_identifier(
            reference_username,
            field_name="Reference username",
        )
        reference = await get_oracle_reference_user(
            schema_connection,
            reference_username,
        )
        for role in reference.get("roles", []):
            sensitive = bool(
                role.get("sensitive")
                or is_sensitive_reference_role(role.get("name", ""))
            )
            preview_roles.append(
                ProvisioningPreviewRole(
                    name=role["name"],
                    sensitive=sensitive,
                    will_copy=not sensitive,
                )
            )
        warnings.extend(reference.get("warnings") or [])

    now = datetime.now(timezone.utc)
    form_values = {
        "first_name": first_name,
        "middle_name": middle_name,
        "last_name": last_name,
        "employee_id": employee_id,
        "reference_user": reference_username,
        "requestor": _clean_optional(data.requestor),
        "request_reference": _clean_optional(data.request_reference),
        "remarks": _clean_optional(data.remarks),
    }
    generated_values = {
        "username": username,
        "password": data.password,
        "operator_username": operator.username,
        "requester_ip": requester_ip,
        "current_datetime": now,
    }

    table_steps: list[ProvisioningPreviewTableStep] = []
    has_conflict = False
    for index, step in enumerate(profile.get("table_steps") or [], start=1):
        step_connection = await get_database_connection(database, step["connection_id"])
        columns: list[ProvisioningPreviewColumn] = []
        raw_values: dict[str, object] = {}

        for mapping in step.get("mappings") or []:
            kind = mapping.get("value_kind", "omit")
            if kind == "omit":
                continue

            column_name = mapping.get("column_name", "")
            if kind == "form":
                key = mapping.get("value_key")
                value = form_values.get(key)
                raw_values[column_name] = value
                columns.append(
                    ProvisioningPreviewColumn(
                        column_name=column_name,
                        source=f"Form · {key}",
                        display_value=_display_value(value),
                    )
                )
            elif kind == "generated":
                key = mapping.get("value_key")
                value = generated_values.get(key)
                raw_values[column_name] = value
                sensitive = key == "password"
                columns.append(
                    ProvisioningPreviewColumn(
                        column_name=column_name,
                        source=f"Generated · {key}",
                        display_value=(
                            "•••••••• (provisioned password)"
                            if sensitive
                            else _display_value(value)
                        ),
                        sensitive=sensitive,
                    )
                )
            elif kind == "sequence":
                sequence = mapping.get("value_key", "")
                columns.append(
                    ProvisioningPreviewColumn(
                        column_name=column_name,
                        source="Oracle sequence",
                        display_value=f'{step["owner"]}.{sequence}.NEXTVAL',
                        expression=True,
                    )
                )
            elif kind == "custom":
                value = mapping.get("custom_value")
                raw_values[column_name] = value
                columns.append(
                    ProvisioningPreviewColumn(
                        column_name=column_name,
                        source="Custom literal",
                        display_value=value,
                    )
                )
            elif kind == "null":
                columns.append(
                    ProvisioningPreviewColumn(
                        column_name=column_name,
                        source="NULL",
                        display_value="NULL",
                        expression=True,
                    )
                )

        match_columns = effective_match_columns(step)
        match_values = {column: raw_values.get(column) for column in match_columns}
        existing_rows = await count_oracle_rows_by_match(
            step_connection,
            owner=step["owner"],
            table_name=step["table_name"],
            match_values=match_values,
        )
        if existing_rows == 0:
            planned_action = "insert"
        elif existing_rows == 1:
            planned_action = "update"
        else:
            planned_action = "conflict"
            has_conflict = True
            warnings.append(
                f'Table step {index} matched {existing_rows} rows; execution must stop until the duplicate identity is resolved.'
            )

        table_steps.append(
            ProvisioningPreviewTableStep(
                index=index,
                name=step["name"],
                connection_id=step["connection_id"],
                connection_name=step_connection.get("name", step["connection_id"]),
                owner=step["owner"],
                table_name=step["table_name"],
                match_columns=match_columns,
                match_values={
                    column: _display_value(value)
                    for column, value in match_values.items()
                },
                existing_rows=existing_rows,
                planned_action=planned_action,
                columns=columns,
            )
        )

    ldap_preview = ProvisioningPreviewLdap(enabled=False)
    if profile.get("ldap_enabled"):
        ldap_profile = await get_ldap_profile_document(
            database, profile["ldap_profile_id"]
        )
        # Render with the real values only to validate the configured template.
        # The rendered LDIF is intentionally not returned by the dry-run endpoint
        # because it contains the password.
        render_ldif(
            ldap_profile.get("ldif_template") or DEFAULT_LDIF_TEMPLATE,
            username=username,
            password=data.password,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            employee_id=employee_id,
            base_dn=ldap_profile.get("base_dn", ""),
        )
        ldap_preview = ProvisioningPreviewLdap(
            enabled=True,
            profile_id=profile["ldap_profile_id"],
            profile_name=ldap_profile.get("name", "LDAP"),
            filename=f"{username}.ldif",
            template_valid=True,
        )

    return ProvisioningPreviewResponse(
        dry_run=True,
        ready_to_execute=not has_conflict,
        profile_id=str(profile["_id"]),
        profile_name=profile["name"],
        schema_connection_id=profile["schema_connection_id"],
        schema_connection_name=schema_connection.get(
            "name", profile["schema_connection_id"]
        ),
        username=username,
        account_exists=account_exists,
        account_action="alter" if account_exists else "create",
        requester_ip=requester_ip,
        operator_username=operator.username,
        generated_at=now,
        reference_user=(reference.get("username") if reference else None),
        default_tablespace=(reference.get("default_tablespace") if reference else None),
        temporary_tablespace=(
            reference.get("temporary_tablespace") if reference else None
        ),
        oracle_profile=(reference.get("profile") if reference else None),
        roles=preview_roles,
        table_steps=table_steps,
        ldap=ldap_preview,
        warnings=warnings,
    )
