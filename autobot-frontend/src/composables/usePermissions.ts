// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Permission Management Composable
 *
 * Provides role-based access control for Vue components.
 * Maps to backend RBAC system (autobot_shared/auth/permissions.py).
 *
 * Issue #683: Role-Based Component Access
 * #16243: previously hand-rolled its own `users:read`-style vocabulary that
 * shared nothing with the backend's `Permission` strings
 * (`autobot_shared/auth/permissions.py`, e.g. `admin.users.read`) -- a
 * control could be shown to a role the backend refuses, or hidden from one
 * it would allow. `Permission` is now generated from that same source
 * (`@/types/_generated/workflow`, same pipeline as `Role`, #14937); every
 * string used below is a member of that union, so an invented value or a
 * typo fails to compile instead of silently diverging again.
 *
 * `ROLE_PERMISSIONS` below is still a hand-curated SUBSET of the backend's
 * 55 permissions -- the ones with a corresponding UI surface today (most of
 * `sandbox.*`/`batch.*`/`mcp.*` have none). The backend's own
 * `ROLE_PERMISSIONS` dict grants a much larger, security-reviewed set per
 * role (see its own extensive comments, especially why `superadmin` holds
 * NONE); this file does not attempt to mirror that exactly; it curates
 * which of the real permissions this composable's callers would need. The
 * backend remains the actual authority regardless of what this returns.
 *
 * The old vocabulary's `chat:*`/`teams:*`/`settings:*`/`audit:*` categories
 * are dropped, not translated: the backend has no `Permission` member for
 * any of them (confirmed against the full enum). Gating a real UI control
 * on one of those concerns needs a real backend permission -- inventing a
 * frontend-only string would repeat exactly the bug this issue is about.
 */

import { computed } from 'vue'
import { useUserStore } from '@/stores/useUserStore'
import type { Role, Permission } from '@/types/_generated/workflow'

export type { Permission }

const ADMIN_PERMISSIONS: Permission[] = [
  'admin.users.read',
  'admin.users.write',
  'admin.config.read',
  'admin.config.write',
  'admin.system',
  'knowledge.read',
  'knowledge.write',
  'knowledge.delete',
  'knowledge.manage',
  'agent.view',
  'agent.execute',
  'agent.manage',
  'files.view',
  'files.download',
  'files.upload',
  'files.delete',
  'files.manage',
  'security.view',
  'security.audit',
  'security.manage'
]

const USER_PERMISSIONS: Permission[] = [
  'knowledge.read',
  'knowledge.write',
  'agent.view',
  'agent.execute',
  'files.view',
  'files.download',
  'files.upload'
]

const READONLY_PERMISSIONS: Permission[] = ['knowledge.read', 'files.view', 'files.download']

/**
 * Role-to-permission mapping, keyed by the generated canonical `Role` (#14937).
 *
 * `Record<Role, ...>` is the point: a role the backend adds fails to compile here
 * until it is given an entry, instead of silently falling to the signed-out set --
 * which is what `operator`, `analyst`, `editor` and `superadmin` all did before #14937.
 *
 * - `superadmin` mirrors `admin`'s frontend set here: it is an administrative
 *   predicate (`is_admin_role()`), and `isAdmin` short-circuits every check
 *   in this file anyway, so it never actually reads `permissions.value`.
 *   (The backend's own `ROLE_PERMISSIONS[Role.SUPERADMIN]` is deliberately
 *   `[]` -- a different, security-reviewed question this file doesn't
 *   answer; see that dict's own comment.)
 * - `operator`, `analyst` and `editor` each get the `user` set here.
 */
export const ROLE_PERMISSIONS: Record<Role, Permission[]> = {
  admin: ADMIN_PERMISSIONS,
  superadmin: ADMIN_PERMISSIONS,
  operator: USER_PERMISSIONS,
  analyst: USER_PERMISSIONS,
  editor: USER_PERMISSIONS,
  user: USER_PERMISSIONS,
  readonly: READONLY_PERMISSIONS
}

/**
 * What the UI offers before anyone signs in. Not a role -- the backend removed
 * `guest` (#744) -- so it is no longer spelled as one (#14937).
 */
export const UNAUTHENTICATED_PERMISSIONS: Permission[] = ['knowledge.read', 'files.view']

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
 * if (hasPermission('admin.system')) { ... }
 *
 * // Check multiple (any)
 * if (hasAnyPermission(['files.upload', 'files.delete'])) { ... }
 *
 * // Check multiple (all)
 * if (hasAllPermissions(['knowledge.read', 'knowledge.write'])) { ... }
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
   * Check if user can access a resource with given action, e.g.
   * `canAccess('knowledge', 'read')` -> checks `'knowledge.read'`, matching
   * the backend's `Permission` separator (#16243 -- the old `:` separator
   * matched nothing real either).
   */
  const canAccess = (resource: string, action: string): boolean => {
    const permission = `${resource}.${action}` as Permission
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
    canAccess
  }
}

export default usePermissions
