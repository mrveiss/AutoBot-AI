// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The one permission-gated /admin section (#19833, epic #19829, ADR-011).
 *
 * `/admin` is a parent record rendering AdminLayout; the 9 pre-existing admin
 * routes are its children with their paths unchanged, so every old URL still
 * resolves to the same component. They move to domain paths later (#17814).
 * Split out of router/index.ts, which is at its size ceiling, as the place
 * admin routes are added; index.ts only spreads `adminRoutes` and calls
 * `resolveAdminPermissionRedirect` from its guard.
 */
import type { RouteLocationNormalized, RouteLocationRaw, RouteRecordRaw } from 'vue-router'

/**
 * The permission that opens the /admin section. The admin and operator roles hold
 * it, but every child route keeps `meta.admin` (an administrative role), so an
 * operator enters the parent and every page under it still sends them to /home.
 */
export const ADMIN_SECTION_PERMISSION = 'service.management'

/** Auth facts the admin gate reads, as exposed by `useUserStore()`. */
export interface AdminAccessState {
  isAuthenticated: boolean
  isAdmin: boolean
  hasServiceManagement: boolean
}

/** Admin-only child meta: the fields every child repeats. */
const adminMeta = (title: string, extra: Record<string, unknown> = {}) => ({
  title,
  hideInNav: true,
  requiresAuth: true,
  admin: true,
  ...extra,
})

export const adminChildren: RouteRecordRaw[] = [
  { path: '', redirect: { name: 'admin-users' } },
  {
    path: 'users', // Issue #1801: Admin User Management
    name: 'admin-users',
    component: () => import('@/views/AdminUsersView.vue'),
    meta: adminMeta('User Management', {
      icon: 'fas fa-users',
      description: 'Manage users, roles, and account status',
      hideInNav: false,
    }),
  },
  {
    path: 'sandbox', // Issue #7773: Sandbox file inspector
    name: 'admin-sandbox',
    component: () => import('@/views/AdminSandboxView.vue'),
    meta: adminMeta('Sandbox Inspector', { description: 'Browse code-execution sandbox files' }),
  },
  {
    path: 'advanced-control', // Issue #12162: takeover approval queue
    name: 'admin-advanced-control',
    component: () => import('@/views/AdvancedControlView.vue'),
    meta: adminMeta('Advanced Control', {
      description: 'Takeover approval queue, streaming, and monitoring',
    }),
  },
  {
    path: 'budget-policies', // GH#6470: Budget policy management
    name: 'budget-policies',
    component: () => import('@/views/BudgetPolicies.vue'),
    meta: adminMeta('Budget Policies', {
      description: 'Manage agent spend thresholds and auto-pause rules',
    }),
  },
  {
    path: 'system-health', // Issue #10932: CONTENT_REACH probe
    name: 'admin-system-health',
    component: () => import('@/views/SystemHealthView.vue'),
    meta: adminMeta('System Health'),
  },
  {
    path: 'provider-fallback', // Issue #11996: provider-fallback observability
    name: 'admin-provider-fallback',
    component: () => import('@/views/ProviderFallbackView.vue'),
    meta: adminMeta('Provider Fallback'),
  },
  {
    path: 'pricing', // Issue #16825: live model-pricing status + override
    name: 'admin-pricing',
    component: () => import('@/views/AdminPricingView.vue'),
    meta: adminMeta('Model Pricing'),
  },
  {
    path: 'mcp-servers', // Issue #16825: external MCP server admin CRUD
    name: 'admin-mcp-servers',
    component: () => import('@/views/AdminMcpServersView.vue'),
    meta: adminMeta('MCP Servers'),
  },
  {
    path: 'conversations', // Issue #17832: org-scoped conversation review (server-gated, audited)
    name: 'admin-conversations',
    component: () => import('@/views/AdminConversationsView.vue'),
    meta: adminMeta('Conversation Review', {
      description: 'Review conversations in your organization',
    }),
  },
  {
    path: 'permission-scopes', // Issue #16825: "coming later" panel
    name: 'admin-permission-scopes',
    component: () => import('@/views/AdminPermissionScopesView.vue'),
    meta: adminMeta('Permission Scopes'),
  },
]

export const adminRoutes: RouteRecordRaw[] = [
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/components/layout/AdminLayout.vue'),
    meta: {
      title: 'Administration',
      hideInNav: true,
      requiresAuth: true,
      permission: ADMIN_SECTION_PERMISSION,
    },
    children: adminChildren,
  },
]

/** True if the user may enter the section: the permission table or an admin role. */
function mayEnterAdmin(state: AdminAccessState): boolean {
  return state.hasServiceManagement || state.isAdmin
}

/**
 * Redirect target for a navigation into a route carrying the /admin section
 * permission, or `null` when allowed or not an /admin route. Fails closed:
 * while auth is unresolved (no session) it never lets the navigation through,
 * and a signed-in user without the permission gets the app's permission-denied
 * page. UI routing only; the backend's own gates remain the authority.
 */
export function resolveAdminPermissionRedirect(
  to: RouteLocationNormalized,
  state: AdminAccessState,
): RouteLocationRaw | null {
  const gated = to.matched.some((r) => r.meta.permission === ADMIN_SECTION_PERMISSION)
  if (!gated) return null
  if (!state.isAuthenticated) return { name: 'login' }
  if (mayEnterAdmin(state)) return null
  return { name: 'permission-denied', query: { required: ADMIN_SECTION_PERMISSION } }
}
