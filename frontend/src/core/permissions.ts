export type UserRole =
  | 'viewer'
  | 'operator'
  | 'admin'

export type Permission =
  | 'monitor:read'
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

export interface PermissionSubject {
  role?: UserRole | string | null
  permissions?: readonly string[] | null
}

/*
 * Fallback role map keeps the frontend compatible during a rolling update.
 * Once /auth/me is served by 7B.2, the backend-supplied permissions array is
 * authoritative and this map is only used for older responses.
 */
const rolePermissions:
  Record<UserRole, ReadonlySet<Permission>> = {
    viewer: new Set([
      'monitor:read',
    ]),

    operator: new Set([
      'monitor:read',
      'connections:test',
      'database:inspect',
      'database:operate',
      'terminal:use',
      'alerts:manage',
    ]),

    admin: new Set([
      'monitor:read',
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
