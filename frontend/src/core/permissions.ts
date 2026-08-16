export type UserRole =
  | 'viewer'
  | 'operator'
  | 'admin'

export type Permission =
  | 'monitor:read'
  | 'connections:test'
  | 'connections:manage'
  | 'servers:manage'
  | 'database:operate'
  | 'users:manage'

const rolePermissions:
  Record<UserRole, ReadonlySet<Permission>> = {
    viewer: new Set([
      'monitor:read',
    ]),

    operator: new Set([
      'monitor:read',
      'connections:test',
      'database:operate',
    ]),

    admin: new Set([
      'monitor:read',
      'connections:test',
      'connections:manage',
      'servers:manage',
      'database:operate',
      'users:manage',
    ]),
  }

export function hasPermission(
  role: UserRole | string | null | undefined,
  permission: Permission,
): boolean {
  if (
    role !== 'viewer' &&
    role !== 'operator' &&
    role !== 'admin'
  ) {
    return false
  }

  return rolePermissions[role].has(permission)
}