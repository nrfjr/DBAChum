export type UserRole =
  | 'viewer'
  | 'operator'
  | 'admin'

export type Permission =
  | 'monitor:read'
  | 'records:manage'
  | 'connections:test'
  | 'connections:manage'
  | 'servers:manage'
  | 'terminal:use'
  | 'database:inspect'
  | 'database:operate'
  | 'alerts:manage'
  | 'notifications:manage'
  | 'users:manage'
  | 'provisioning:manage'
  | 'ldap:manage'
  | 'system:manage'

export interface PermissionSubject {
  role?: UserRole | string | null
  permissions?: readonly string[] | null
}

const rolePermissions:
  Record<UserRole, ReadonlySet<Permission>> = {
    viewer: new Set([
      'monitor:read',
    ]),

    operator: new Set([
      'monitor:read',
      'records:manage',
      'connections:test',
      'database:inspect',
      'database:operate',
      'terminal:use',
      'alerts:manage',
    ]),

    admin: new Set([
      'monitor:read',
      'records:manage',
      'connections:test',
      'connections:manage',
      'servers:manage',
      'terminal:use',
      'database:inspect',
      'database:operate',
      'alerts:manage',
      'notifications:manage',
      'users:manage',
      'provisioning:manage',
      'ldap:manage',
      'system:manage',
    ]),
  }

export function hasPermission(
  subject: PermissionSubject | UserRole | string | null | undefined,
  permission: Permission,
): boolean {
  if (subject && typeof subject === 'object') {
    if (Array.isArray(subject.permissions)) {
      return subject.permissions.includes(permission)
    }

    subject = subject.role
  }

  if (
    subject !== 'viewer' &&
    subject !== 'operator' &&
    subject !== 'admin'
  ) {
    return false
  }

  return rolePermissions[subject].has(permission)
}
