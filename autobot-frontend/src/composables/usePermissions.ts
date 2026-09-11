// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Permission Management Composable
 *
 * Provides role-based access control for Vue components.
 * Maps to backend RBAC system (src/user_management/models/role.py).
 *
 * Issue #683: Role-Based Component Access
 */

import { computed } from 'vue'
import { useUserStore } from '@/stores/useUserStore'
import type { Role } from '@/types/_generated/workflow'

/**
 * The frontend's permission vocabulary. It does NOT match the backend's
 * `Permission` strings (`autobot_shared/auth/permissions.py`) -- #16243.
 */
export const PERMISSIONS = {
  // User management
  USERS_READ: 'users:read',
  USERS_CREATE: 'users:create',
  USERS_UPDATE: 'users:update',
  USERS_DELETE: 'users:delete',

  // Team management
  TEAMS_READ: 'teams:read',
  TEAMS_CREATE: 'teams:create',
  TEAMS_MANAGE: 'teams:manage',
  TEAMS_DELETE: 'teams:delete',

  // Knowledge base
  KNOWLEDGE_READ: 'knowledge:read',
  KNOWLEDGE_WRITE: 'knowledge:write',
  KNOWLEDGE_DELETE: 'knowledge:delete',

  // Chat
  CHAT_USE: 'chat:use',
  CHAT_HISTORY: 'chat:history',

  // Files
  FILES_VIEW: 'files:view',
  FILES_UPLOAD: 'files:upload',
  FILES_DOWNLOAD: 'files:download',
  FILES_DELETE: 'files:delete',

  // Settings
  SETTINGS_READ: 'settings:read',
  SETTINGS_WRITE: 'settings:write',

  // Admin
  ADMIN_ACCESS: 'admin:access',
  ADMIN_USERS: 'admin:users',
  ADMIN_ORGANIZATION: 'admin:organization',

  // Audit (Issue #683: Role-Based Access Control)
  AUDIT_READ: 'audit:read',
  AUDIT_WRITE: 'audit:write',
} as const

export type Permission = typeof PERMISSIONS[keyof typeof PERMISSIONS]

const ADMIN_PERMISSIONS: Permission[] = [
  PERMISSIONS.USERS_READ, PERMISSIONS.USERS_CREATE, PERMISSIONS.USERS_UPDATE, PERMISSIONS.USERS_DELETE,
  PERMISSIONS.TEAMS_READ, PERMISSIONS.TEAMS_CREATE, PERMISSIONS.TEAMS_MANAGE, PERMISSIONS.TEAMS_DELETE,
  PERMISSIONS.KNOWLEDGE_READ, PERMISSIONS.KNOWLEDGE_WRITE, PERMISSIONS.KNOWLEDGE_DELETE,
  PERMISSIONS.CHAT_USE, PERMISSIONS.CHAT_HISTORY,
  PERMISSIONS.FILES_VIEW, PERMISSIONS.FILES_UPLOAD, PERMISSIONS.FILES_DOWNLOAD, PERMISSIONS.FILES_DELETE,
  PERMISSIONS.SETTINGS_READ, PERMISSIONS.SETTINGS_WRITE,
  PERMISSIONS.ADMIN_ACCESS, PERMISSIONS.ADMIN_USERS, PERMISSIONS.ADMIN_ORGANIZATION,
  PERMISSIONS.AUDIT_READ, PERMISSIONS.AUDIT_WRITE,
]

const USER_PERMISSIONS: Permission[] = [
  PERMISSIONS.USERS_READ,
  PERMISSIONS.TEAMS_READ,
  PERMISSIONS.KNOWLEDGE_READ, PERMISSIONS.KNOWLEDGE_WRITE,
  PERMISSIONS.CHAT_USE, PERMISSIONS.CHAT_HISTORY,
  PERMISSIONS.FILES_VIEW, PERMISSIONS.FILES_UPLOAD, PERMISSIONS.FILES_DOWNLOAD,
  PERMISSIONS.SETTINGS_READ,
]

/**
 * Role-to-permission mapping, keyed by the generated canonical `Role` (#14937).
 *
 * `Record<Role, ...>` is the point: a role the backend adds fails to compile here
 * until it is given an entry, instead of silently falling to the signed-out set --
 * which is what `operator`, `analyst`, `editor` and `superadmin` all did.
 *
 * - `superadmin` mirrors `admin`: it is an administrative predicate
 *   (`is_admin_role()`), and `isAdmin` short-circuits every check anyway.
 * - `operator`, `analyst` and `editor` each hold a superset of the backend USER
 *   role's permissions (`ROLE_PERMISSIONS` in `autobot_shared/auth/permissions.py`),
 *   so they get this map's `user` set.
 *
 * The permission strings themselves are the frontend's own vocabulary, not the
 * backend's `Permission` values -- #16243 tracks converging them.
 */
export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: ADMIN_PERMISSIONS,
  superadmin: ADMIN_PERMISSIONS,
  operator: USER_PERMISSIONS,
  analyst: USER_PERMISSIONS,
  editor: USER_PERMISSIONS,
  user: USER_PERMISSIONS,
  readonly: [
    PERMISSIONS.USERS_READ,
    PERMISSIONS.TEAMS_READ,
    PERMISSIONS.KNOWLEDGE_READ,
    PERMISSIONS.CHAT_HISTORY,
    PERMISSIONS.FILES_VIEW, PERMISSIONS.FILES_DOWNLOAD,
    PERMISSIONS.SETTINGS_READ,
  ],
}

/**
 * What the UI offers before anyone signs in. Not a role -- the backend removed
 * `guest` (#744) -- so it is no longer spelled as one (#14937).
 */
export const UNAUTHENTICATED_PERMISSIONS: Permission[] = [
  PERMISSIONS.CHAT_USE,
  PERMISSIONS.KNOWLEDGE_READ,
  PERMISSIONS.FILES_VIEW,
]

function isRole(value: string): value is Role {
  return Object.prototype.hasOwnProperty.call(ROLE_PERMISSIONS, value)
}

/**
 * Permissions for a role. No role, or one outside the canonical vocabulary, gets
 * the signed-out set -- fail-safe: an unknown role sees less, never more.
 */
export function getPermissionsForRole(role: string | null | undefined): Permission[] {
  const key = role?.toLowerCase()
  return key && isRole(key) ? ROLE_PERMISSIONS[key] : UNAUTHENTICATED_PERMISSIONS
}

/**
 * Permission checking composable
 *
 * Usage:
 * ```typescript
 * const { hasPermission, hasAnyPermission, canAccess } = usePermissions()
 *
 * // Check single permission
 * if (hasPermission('admin:access')) { ... }
 *
 * // Check multiple (any)
 * if (hasAnyPermission(['files:upload', 'files:delete'])) { ... }
 *
 * // Check multiple (all)
 * if (hasAllPermissions(['users:read', 'users:update'])) { ... }
 * ```
 */
export function usePermissions() {
  const userStore = useUserStore()

  /**
   * Current user's permissions based on their role
   */
  const permissions = computed<Permission[]>(() => getPermissionsForRole(userStore.currentUser?.role))

  /**
   * Check if user has a specific permission
   */
  const hasPermission = (permission: Permission | string): boolean => {
    // Admin always has all permissions
    if (userStore.isAdmin) return true
    return permissions.value.includes(permission as Permission)
  }

  /**
   * Check if user has ANY of the specified permissions
   */
  const hasAnyPermission = (perms: (Permission | string)[]): boolean => {
    if (userStore.isAdmin) return true
    return perms.some(p => permissions.value.includes(p as Permission))
  }

  /**
   * Check if user has ALL of the specified permissions
   */
  const hasAllPermissions = (perms: (Permission | string)[]): boolean => {
    if (userStore.isAdmin) return true
    return perms.every(p => permissions.value.includes(p as Permission))
  }

  /**
   * Check if user can access a resource with given action
   * E.g., canAccess('files', 'upload')
   */
  const canAccess = (resource: string, action: string): boolean => {
    const permission = `${resource}:${action}` as Permission
    return hasPermission(permission)
  }

  /**
   * Check if user is admin
   */
  const isAdmin = computed(() => userStore.isAdmin)

  /**
   * Check if user is authenticated
   */
  const isAuthenticated = computed(() => userStore.isAuthenticated)

  /**
   * Current user's role
   */
  // #14937: null when signed out -- there is no `guest` role to report.
  const role = computed<Role | null>(() => userStore.currentUser?.role ?? null)

  return {
    // State
    permissions,
    role,
    isAdmin,
    isAuthenticated,

    // Permission checks
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    canAccess,

    // Constants for convenience
    PERMISSIONS,
  }
}

export default usePermissions
