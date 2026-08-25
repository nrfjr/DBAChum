from enum import Enum

from app.schemas.user import UserRole


class Permission(str, Enum):
    MONITOR_READ = "monitor:read"

    CONNECTION_TEST = "connections:test"
    CONNECTION_MANAGE = "connections:manage"

    SERVER_MANAGE = "servers:manage"

    DBA_OPERATE = "database:operate"

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
            Permission.DBA_OPERATE,
        }
    ),

    UserRole.ADMIN: frozenset(
        {
            Permission.MONITOR_READ,

            Permission.CONNECTION_TEST,
            Permission.CONNECTION_MANAGE,

            Permission.SERVER_MANAGE,

            Permission.DBA_OPERATE,

            Permission.USER_MANAGE,
            Permission.PROVISIONING_MANAGE,
            Permission.LDAP_MANAGE,
        }
    ),
}


def has_permission(
    role: UserRole | str,
    permission: Permission,
) -> bool:
    try:
        normalized_role = UserRole(role)
    except ValueError:
        return False

    return permission in ROLE_PERMISSIONS.get(
        normalized_role,
        frozenset(),
    )