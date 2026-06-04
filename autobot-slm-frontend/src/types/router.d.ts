// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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
