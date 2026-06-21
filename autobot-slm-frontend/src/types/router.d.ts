// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** Route title for document.title and breadcrumbs */
    title?: string

    /** Whether auth is required (false = public route, default = true) */
    requiresAuth?: boolean

    /** Parent route name for breadcrumb hierarchy */
    parent?: string

    /** Whether route requires admin role */
    admin?: boolean
  }
}

export {}
