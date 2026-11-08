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
 * it would allow. `Permission` is generated from that same source
 * (`@/types/_generated/workflow`, same pipeline as `Role`, #14937), so an
 * invented value or a typo fails to compile instead of silently diverging.
 *
 * `ROLE_PERMISSIONS` is the backend's own grant map, generated too (#16491):
 * every role holds exactly what the backend's `ROLE_PERMISSIONS` grants it,
 * with no hand-curated subset left to drift. That includes `superadmin`,
 * which the backend derives from admin's set (#19125, owner decision
 * 2026-10-21), so it holds every permission admin does; the administrative
 * short-circuit (`userStore.isAdmin` / `isAdminRole`) still admits it as
 * `is_admin_role()` does on the backend.
 *
 * The backend remains the authority regardless of what this returns; this
 * only decides what the UI offers.
 */

import { computed } from 'vue'
import { useUserStore } from '@/stores/useUserStore'
import { ROLE_PERMISSIONS, type Permission, type Role } from '@/types/_generated/workflow'

export type { Permission }
export { ROLE_PERMISSIONS }

/**
 * What the UI offers before anyone signs in. Not a role -- the backend removed
 * `guest` (#744) -- so there is no backend grant to generate it from, and it
 * stays written here (#14937).
 */
export const UNAUTHENTICATED_PERMISSIONS: readonly Permission[] = ['knowledge.read', 'files.view']

function isRole(value: string): value is Role {
  return Object.prototype.hasOwnProperty.call(ROLE_PERMISSIONS, value)
}

/**
 * Permissions for a role, straight from the backend's grant map. No role, or one
 * outside the canonical vocabulary, gets the signed-out set -- fail-safe: an
 * unknown role sees less, never more.
 */
export function getPermissionsForRole(role: string | null | undefined): readonly Permission[] {
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
  const permissions = computed<readonly Permission[]>(() => getPermissionsForRole(userStore.currentUser?.role))

  /**
   * Check if user has a specific permission
   */
  const hasPermission = (permission: Permission | string): boolean => {
    // Admin always has all permissions
    if (userStore.isAdmin) return true
    return permissions.value.includes(permission as Permission)
  }

  /**
   * Does the caller's ROLE TABLE hold this permission -- with no
   * administrative override.
   *
   * Use this, not `hasPermission`, wherever the UI must agree with a backend
   * gate that asks `role_has_permission`. #13854 removed the administrative
   * short-circuit from that predicate on purpose, because it made the
   * predicate the most permissive permission source in the system. So
   * `hasPermission`'s `isAdmin` bypass disagrees with every such gate for any
   * admin role whose table entry lacks the permission.
   *
   * Before #19125 `superadmin` was the live case: its `ROLE_PERMISSIONS`
   * entry was empty, so the desktop socket refused it (#17054) while
   * `hasPermission('mcp.desktop.control')` returned true (#17370). Its entry is
   * now derived from admin's, so the two agree; prefer this method anyway for a
   * control that mirrors a `role_has_permission` gate.
   *
   * `hasPermission` is left alone deliberately -- its administrative override
   * is relied on by call sites this did not audit.
   */
  const holdsPermission = (permission: Permission | string): boolean =>
    permissions.value.includes(permission as Permission)

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
    holdsPermission,
    hasAnyPermission,
    hasAllPermissions,
    canAccess
  }
}

export default usePermissions
