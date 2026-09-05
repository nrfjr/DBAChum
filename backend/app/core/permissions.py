from enum import Enum

from app.schemas.user import UserRole


class Permission(str, Enum):
    """Stable DBAChum authorization boundaries.

    Monitoring is intentionally separate from DBA inspection and mutation.
    Settings/configuration permissions remain administrator-only, while
    operators can perform approved day-to-day DBA work.
    """

    MONITOR_READ = "monitor:read"

    CONNECTION_TEST = "connections:test"
    CONNECTION_MANAGE = "connections:manage"

    SERVER_MANAGE = "servers:manage"
    TERMINAL_USE = "terminal:use"

    DATABASE_INSPECT = "database:inspect"
    DBA_OPERATE = "database:operate"

    ALERT_MANAGE = "alerts:manage"
    NOTIFICATION_MANAGE = "notifications:manage"

    USER_MANAGE = "users:manage"
    PROVISIONING_MANAGE = "provisioning:manage"
    LDAP_MANAGE = "ldap:manage"


ROLE_PERMISSIONS: dict[
    UserRole,
    frozenset[Permission],
] = {
    UserRole.VIEWER: frozenset(
        {
            Permission.MONITOR_READ,
        }
    ),

    UserRole.OPERATOR: frozenset(
        {
            Permission.MONITOR_READ,
            Permission.CONNECTION_TEST,
            Permission.DATABASE_INSPECT,
            Permission.DBA_OPERATE,
            Permission.TERMINAL_USE,
            Permission.ALERT_MANAGE,
        }
    ),

    UserRole.ADMIN: frozenset(
        {
            Permission.MONITOR_READ,

            Permission.CONNECTION_TEST,
            Permission.CONNECTION_MANAGE,

            Permission.SERVER_MANAGE,
            Permission.TERMINAL_USE,

            Permission.DATABASE_INSPECT,
            Permission.DBA_OPERATE,

            Permission.ALERT_MANAGE,
            Permission.NOTIFICATION_MANAGE,

            Permission.USER_MANAGE,
            Permission.PROVISIONING_MANAGE,
            Permission.LDAP_MANAGE,
        }
    ),
}


def permissions_for_role(
    role: UserRole | str,
) -> frozenset[Permission]:
    try:
        normalized_role = UserRole(role)
    except ValueError:
        return frozenset()

    return ROLE_PERMISSIONS.get(
        normalized_role,
        frozenset(),
    )


def permission_values_for_role(
    role: UserRole | str,
) -> list[str]:
    return sorted(
        permission.value
        for permission in permissions_for_role(role)
    )


def has_permission(
    role: UserRole | str,
    permission: Permission,
) -> bool:
    return permission in permissions_for_role(role)
