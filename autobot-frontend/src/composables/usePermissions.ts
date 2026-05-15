// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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

/**
 * System permissions matching backend SYSTEM_PERMISSIONS
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

/**
 * Role-to-permission mapping matching backend SYSTEM_ROLES
 */
export const ROLE_PERMISSIONS: Record<string, Permission[]> = {
  admin: [
    PERMISSIONS.USERS_READ, PERMISSIONS.USERS_CREATE, PERMISSIONS.USERS_UPDATE, PERMISSIONS.USERS_DELETE,
    PERMISSIONS.TEAMS_READ, PERMISSIONS.TEAMS_CREATE, PERMISSIONS.TEAMS_MANAGE, PERMISSIONS.TEAMS_DELETE,
    PERMISSIONS.KNOWLEDGE_READ, PERMISSIONS.KNOWLEDGE_WRITE, PERMISSIONS.KNOWLEDGE_DELETE,
    PERMISSIONS.CHAT_USE, PERMISSIONS.CHAT_HISTORY,
    PERMISSIONS.FILES_VIEW, PERMISSIONS.FILES_UPLOAD, PERMISSIONS.FILES_DOWNLOAD, PERMISSIONS.FILES_DELETE,
    PERMISSIONS.SETTINGS_READ, PERMISSIONS.SETTINGS_WRITE,
    PERMISSIONS.ADMIN_ACCESS, PERMISSIONS.ADMIN_USERS, PERMISSIONS.ADMIN_ORGANIZATION,
    PERMISSIONS.AUDIT_READ, PERMISSIONS.AUDIT_WRITE,
  ],
  user: [
    PERMISSIONS.USERS_READ,
    PERMISSIONS.TEAMS_READ,
    PERMISSIONS.KNOWLEDGE_READ, PERMISSIONS.KNOWLEDGE_WRITE,
    PERMISSIONS.CHAT_USE, PERMISSIONS.CHAT_HISTORY,
    PERMISSIONS.FILES_VIEW, PERMISSIONS.FILES_UPLOAD, PERMISSIONS.FILES_DOWNLOAD,
    PERMISSIONS.SETTINGS_READ,
  ],
  readonly: [
    PERMISSIONS.USERS_READ,
    PERMISSIONS.TEAMS_READ,
    PERMISSIONS.KNOWLEDGE_READ,
    PERMISSIONS.CHAT_HISTORY,
    PERMISSIONS.FILES_VIEW, PERMISSIONS.FILES_DOWNLOAD,
    PERMISSIONS.SETTINGS_READ,
  ],
  viewer: [ // Alias for readonly
    PERMISSIONS.USERS_READ,
    PERMISSIONS.TEAMS_READ,
    PERMISSIONS.KNOWLEDGE_READ,
    PERMISSIONS.CHAT_HISTORY,
    PERMISSIONS.FILES_VIEW, PERMISSIONS.FILES_DOWNLOAD,
    PERMISSIONS.SETTINGS_READ,
  ],
  guest: [
    PERMISSIONS.CHAT_USE,
    PERMISSIONS.KNOWLEDGE_READ,
    PERMISSIONS.FILES_VIEW,
  ],
}

/**
 * Get permissions for a given role
 */
export function getPermissionsForRole(role: string): Permission[] {
  return ROLE_PERMISSIONS[role.toLowerCase()] || ROLE_PERMISSIONS.guest
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
  const permissions = computed<Permission[]>(() => {
    const role = userStore.currentUser?.role || 'guest'
    return getPermissionsForRole(role)
  })

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
  const role = computed(() => userStore.currentUser?.role || 'guest')

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
