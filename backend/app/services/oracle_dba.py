from app.connectors.oracle_activity import (
    get_oracle_activity,
)
from app.connectors.oracle_sessions import (
    get_oracle_sessions,
)
from app.connectors.oracle_storage import (
    get_oracle_storage,
)
from app.connectors.oracle_users import (
    get_oracle_users,
)
from app.connectors.oracle_provisioning import (
    OracleUserProvisioningPartialError,
    create_oracle_user,
    get_oracle_reference_user,
    is_sensitive_reference_role,
    normalize_oracle_identifier,
    oracle_user_exists,
)
from app.core.exceptions import AppError
from app.schemas.database_action import (
    DatabaseActionRisk,
    DatabaseActionStatus,
)
from app.schemas.oracle_dba import OracleCreateUserRequest
from app.schemas.user import UserResponse
from app.services.database_actions import (
    finish_database_action,
    start_database_action,
)
from app.services.database_connections import (
    get_database_connection,
)


async def get_oracle_target(
    database,
    connection_id: str,
):
    connection = await get_database_connection(
        database,
        connection_id,
    )

    if connection["engine"] != "oracle":
        raise AppError(
            "This utility is only available "
            "for Oracle connections.",
            code="ORACLE_UTILITY_NOT_AVAILABLE",
            status_code=400,
        )

    if not connection.get("enabled", True):
        raise AppError(
            "Monitoring is disabled for "
            "this connection.",
            code="CONNECTION_DISABLED",
            status_code=400,
        )

    return connection


async def load_oracle_sessions(
    database,
    connection_id: str,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    return await get_oracle_sessions(
        connection
    )


async def load_oracle_storage(
    database,
    connection_id: str,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    return await get_oracle_storage(
        connection
    )


async def load_oracle_activity(
    database,
    connection_id: str,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    return await get_oracle_activity(
        connection
    )

async def load_oracle_users(
    database,
    connection_id: str,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    return await get_oracle_users(
        connection
    )

async def load_oracle_reference_user(
    database,
    connection_id: str,
    username: str,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    return await get_oracle_reference_user(
        connection,
        username,
    )


async def provision_oracle_user(
    database,
    connection_id: str,
    data: OracleCreateUserRequest,
    operator: UserResponse,
):
    connection = await get_oracle_target(
        database,
        connection_id,
    )

    username = normalize_oracle_identifier(
        data.username,
        field_name="Username",
    )

    if await oracle_user_exists(
        connection,
        username,
    ):
        raise AppError(
            "A database account with this username already exists.",
            code="ORACLE_USER_ALREADY_EXISTS",
            status_code=409,
        )

    reference = None
    allowed_roles: set[str] = set()

    if data.reference_username:
        reference = await get_oracle_reference_user(
            connection,
            data.reference_username,
        )

        allowed_roles = {
            role["name"].upper()
            for role in reference["roles"]
        }

    normalized_roles = []

    for role in data.roles:
        normalized_role = normalize_oracle_identifier(
            role,
            field_name="Role",
        )

        if not reference:
            raise AppError(
                "Roles can only be copied from a reviewed reference user in this phase.",
                code="ORACLE_REFERENCE_USER_REQUIRED",
                status_code=400,
            )

        if normalized_role not in allowed_roles:
            raise AppError(
                f"Role {normalized_role} is not granted to the selected reference user.",
                code="ORACLE_REFERENCE_ROLE_MISMATCH",
                status_code=400,
            )

        if is_sensitive_reference_role(
            normalized_role
        ):
            raise AppError(
                f"Role {normalized_role} is classified as sensitive and must be granted manually.",
                code="ORACLE_SENSITIVE_ROLE_BLOCKED",
                status_code=400,
            )

        if normalized_role not in normalized_roles:
            normalized_roles.append(normalized_role)

    default_tablespace = (
        data.default_tablespace
        or (
            reference.get("default_tablespace")
            if reference
            else None
        )
    )

    temporary_tablespace = (
        data.temporary_tablespace
        or (
            reference.get("temporary_tablespace")
            if reference
            else None
        )
    )

    profile = (
        data.profile
        or (
            reference.get("profile")
            if reference
            else None
        )
    )

    details = {
        "reference_username": (
            reference["username"]
            if reference
            else None
        ),
        "roles_requested": normalized_roles,
        "requestor_name": data.requestor_name,
        "connection_auth_mode": connection.get(
            "oracle_auth_mode",
            "normal",
        ),
    }

    audit_id = await start_database_action(
        database,
        connection_id=connection_id,
        engine="oracle",
        action="create_user",
        target=username,
        operator=operator,
        risk=DatabaseActionRisk.SENSITIVE,
        request_reference=data.request_reference,
        before={"exists": False},
        details=details,
    )

    try:
        result = await create_oracle_user(
            connection,
            username=username,
            password=data.password,
            roles=normalized_roles,
            default_tablespace=default_tablespace,
            temporary_tablespace=temporary_tablespace,
            profile=profile,
        )
    except OracleUserProvisioningPartialError as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.PARTIAL,
            after={
                "exists": True,
                "roles_applied": exc.roles_applied,
            },
            error=str(exc),
            details={
                **details,
                "roles_applied": exc.roles_applied,
            },
        )

        raise AppError(
            "The Oracle account was created, but one or more role grants failed. "
            "Review the action history before retrying manually.",
            code="ORACLE_USER_CREATE_PARTIAL",
            status_code=409,
        ) from exc
    except AppError as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            after={"exists": False},
            error=exc.message,
            details=details,
        )
        raise
    except Exception as exc:
        await finish_database_action(
            database,
            audit_id,
            status=DatabaseActionStatus.FAILED,
            after=None,
            error=str(exc),
            details=details,
        )
        raise

    await finish_database_action(
        database,
        audit_id,
        status=DatabaseActionStatus.SUCCEEDED,
        after={
            "exists": True,
            "roles_applied": result["roles_applied"],
            "default_tablespace": result[
                "default_tablespace"
            ],
            "temporary_tablespace": result[
                "temporary_tablespace"
            ],
            "profile": result["profile"],
        },
        details={
            **details,
            "roles_applied": result["roles_applied"],
        },
    )

    return {
        "username": username,
        "roles_applied": result["roles_applied"],
        "audit_id": audit_id,
        "status": "succeeded",
    }

