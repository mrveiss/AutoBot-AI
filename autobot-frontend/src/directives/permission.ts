// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Permission Directive
 *
 * Conditionally renders elements based on user permissions.
 * Issue #683: Role-Based Component Access
 *
 * Usage:
 * ```vue
 * <!-- Hide element if no permission -->
 * <button v-permission="'admin:access'">Admin Panel</button>
 *
 * <!-- Check any of multiple permissions -->
 * <div v-permission:any="['files:upload', 'files:delete']">File Actions</div>
 *
 * <!-- Check all permissions required -->
 * <div v-permission:all="['users:read', 'users:update']">Edit User</div>
 *
 * <!-- Disable instead of hide -->
 * <button v-permission.disable="'settings:write'">Save Settings</button>
 * ```
 */

import type { Directive, DirectiveBinding } from 'vue'
import { getPermissionsForRole, type Permission } from '@/composables/usePermissions'

type PermissionValue = Permission | string | (Permission | string)[]

interface PermissionBinding extends DirectiveBinding<PermissionValue> {
  arg?: 'any' | 'all'
  modifiers: {
    disable?: boolean
  }
}

// Store original display values for proper restoration
const originalDisplayMap = new WeakMap<HTMLElement, string>()

/**
 * Get user role from localStorage/store without using composable
 * This avoids Vue composable lifecycle issues in directives
 */
function getCurrentUserRole(): string {
  try {
    const storedUser = localStorage.getItem('autobot_user')
    if (storedUser) {
      const user = JSON.parse(storedUser)
      return user.role || 'guest'
    }
  } catch {
    // Ignore parse errors
  }
  return 'guest'
}

/**
 * Check if user has a specific permission (standalone function)
 */
function userHasPermission(permission: Permission | string): boolean {
  const role = getCurrentUserRole()
  // Admin always has all permissions
  if (role === 'admin') return true
  const permissions = getPermissionsForRole(role)
  return permissions.includes(permission as Permission)
}

/**
 * Check if user has any of the specified permissions
 */
function userHasAnyPermission(perms: (Permission | string)[]): boolean {
  const role = getCurrentUserRole()
  if (role === 'admin') return true
  const permissions = getPermissionsForRole(role)
  return perms.some(p => permissions.includes(p as Permission))
}

/**
 * Check if user has all of the specified permissions
 */
function userHasAllPermissions(perms: (Permission | string)[]): boolean {
  const role = getCurrentUserRole()
  if (role === 'admin') return true
  const permissions = getPermissionsForRole(role)
  return perms.every(p => permissions.includes(p as Permission))
}

/**
 * Check if user has required permissions based on binding
 */
function checkPermission(binding: PermissionBinding): boolean {
  const value = binding.value

  // Handle array of permissions
  if (Array.isArray(value)) {
    if (binding.arg === 'all') {
      return userHasAllPermissions(value)
    }
    // Default to 'any' for arrays
    return userHasAnyPermission(value)
  }

  // Single permission
  return userHasPermission(value)
}

/**
 * Apply permission check result to element
 */
function applyPermission(el: HTMLElement, binding: PermissionBinding): void {
  const hasPermission = checkPermission(binding)

  if (!hasPermission) {
    if (binding.modifiers.disable) {
      // Disable the element instead of hiding
      el.setAttribute('disabled', 'true')
      el.classList.add('permission-disabled')
      el.style.opacity = '0.5'
      el.style.cursor = 'not-allowed'
      el.style.pointerEvents = 'none'
    } else {
      // Store original display value before hiding
      if (!originalDisplayMap.has(el)) {
        const computedDisplay = getComputedStyle(el).display
        originalDisplayMap.set(el, el.style.display || computedDisplay)
      }
      // Hide the element (default)
      el.style.display = 'none'
      el.classList.add('permission-hidden')
    }
  } else {
    // Restore element
    el.removeAttribute('disabled')
    el.classList.remove('permission-disabled', 'permission-hidden')
    el.style.opacity = ''
    el.style.cursor = ''
    el.style.pointerEvents = ''

    // Restore original display value
    const originalDisplay = originalDisplayMap.get(el)
    if (originalDisplay && originalDisplay !== 'none') {
      el.style.display = originalDisplay
    } else {
      el.style.display = ''
    }
  }
}

/**
 * v-permission directive
 *
 * Note: This directive reads permissions directly from localStorage
 * to avoid Vue composable lifecycle issues. The permission check
 * is re-evaluated on mount and update.
 *
 * For reactive permission changes (e.g., after login/logout),
 * components should force re-render by using :key bindings
 * or the component should re-mount.
 */
export const vPermission: Directive<HTMLElement, PermissionValue> = {
  mounted(el, binding) {
    applyPermission(el, binding as PermissionBinding)
  },

  updated(el, binding) {
    applyPermission(el, binding as PermissionBinding)
  },

  unmounted(el) {
    // Clean up stored display value
    originalDisplayMap.delete(el)
  },
}

export default vPermission
