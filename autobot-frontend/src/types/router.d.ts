// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Vue Router Type Extensions
 *
 * Extends route meta with permission-based access control.
 * Issue #683: Role-Based Component Access
 */

import 'vue-router'
import type { Permission } from '@/composables/usePermissions'

declare module 'vue-router' {
  interface RouteMeta {
    /**
     * Route title displayed in navigation and document title
     */
    title?: string

    /**
     * FontAwesome icon class for navigation
     */
    icon?: string

    /**
     * Description for tooltips and accessibility
     */
    description?: string

    /**
     * Whether authentication is required
     */
    requiresAuth?: boolean

    /**
     * Hide from navigation menu
     */
    hideInNav?: boolean

    /**
     * Parent route name for breadcrumbs
     */
    parent?: string

    /**
     * Single permission required to access this route
     */
    permission?: Permission | string

    /**
     * Multiple permissions - user needs ANY of these
     */
    anyPermissions?: (Permission | string)[]

    /**
     * Multiple permissions - user needs ALL of these
     */
    allPermissions?: (Permission | string)[]

    /**
     * Minimum role required (admin > user > readonly > guest)
     */
    minRole?: 'admin' | 'user' | 'readonly' | 'guest'

    /**
     * Whether this route is admin-only (shorthand for minRole: 'admin')
     */
    adminOnly?: boolean
  }
}

export {}
