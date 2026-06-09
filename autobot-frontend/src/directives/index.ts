// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Vue Directives Registry
 *
 * Exports all custom directives for global registration.
 * Issue #683: Role-Based Component Access
 */

import type { App } from 'vue'
import { vPermission } from './permission'

/**
 * Register all custom directives on the Vue app
 */
export function registerDirectives(app: App): void {
  // v-permission - Role-based access control
  app.directive('permission', vPermission)
}

// Export individual directives for local use
export { vPermission } from './permission'
