// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #19833: the one permission-gated /admin parent. Pins the gate (allowed,
// denied, unresolved auth fails closed), that every pre-existing /admin URL
// still resolves to the same component, and that AdminLayout renders the
// matched child through a nested router-view.

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { RouterView, createMemoryHistory, createRouter } from 'vue-router'
import type { RouteLocationNormalized, RouteRecordNormalized } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { defineComponent, h } from 'vue'
import { routes } from '@/router'
import AdminLayout from '@/components/layout/AdminLayout.vue'
import en from '@/i18n/locales/en.json'
import {
  ADMIN_SECTION_PERMISSION,
  adminChildren,
  adminRoutes,
  resolveAdminPermissionRedirect,
} from '../adminRoutes'

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get: vi.fn().mockResolvedValue([]) }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

const OLD_ADMIN_PATHS: Record<string, string> = {
  '/admin/users': 'admin-users',
  '/admin/sandbox': 'admin-sandbox',
  '/admin/advanced-control': 'admin-advanced-control',
  '/admin/budget-policies': 'budget-policies',
  '/admin/system-health': 'admin-system-health',
  '/admin/provider-fallback': 'admin-provider-fallback',
  '/admin/pricing': 'admin-pricing',
  '/admin/mcp-servers': 'admin-mcp-servers',
  '/admin/permission-scopes': 'admin-permission-scopes',
}

const OLD_COMPONENT_FILES: Record<string, string> = {
  'admin-users': 'AdminUsersView.vue',
  'admin-sandbox': 'AdminSandboxView.vue',
  'admin-advanced-control': 'AdvancedControlView.vue',
  'budget-policies': 'BudgetPolicies.vue',
  'admin-system-health': 'SystemHealthView.vue',
  'admin-provider-fallback': 'ProviderFallbackView.vue',
  'admin-pricing': 'AdminPricingView.vue',
  'admin-mcp-servers': 'AdminMcpServersView.vue',
  'admin-permission-scopes': 'AdminPermissionScopesView.vue',
}

function adminTo(): RouteLocationNormalized {
  const matched = [{ meta: { permission: ADMIN_SECTION_PERMISSION } }, { meta: { admin: true } }]
  return { matched: matched as unknown as RouteRecordNormalized[] } as RouteLocationNormalized
}

const state = (over: Partial<Parameters<typeof resolveAdminPermissionRedirect>[1]>) => ({
  isAuthenticated: true,
  isAdmin: false,
  hasServiceManagement: false,
  ...over,
})

describe('resolveAdminPermissionRedirect (#19833)', () => {
  it('allows a user holding service.management', () => {
    expect(resolveAdminPermissionRedirect(adminTo(), state({ hasServiceManagement: true }))).toBeNull()
  })

  it('allows an administrative role', () => {
    expect(resolveAdminPermissionRedirect(adminTo(), state({ isAdmin: true }))).toBeNull()
  })

  it('sends a signed-in user without the permission to permission-denied', () => {
    expect(resolveAdminPermissionRedirect(adminTo(), state({}))).toEqual({
      name: 'permission-denied',
      query: { required: ADMIN_SECTION_PERMISSION },
    })
  })

  it('fails closed while auth is unresolved, even if the flags read true', () => {
    const unresolved = state({ isAuthenticated: false, isAdmin: true, hasServiceManagement: true })
    expect(resolveAdminPermissionRedirect(adminTo(), unresolved)).toEqual({ name: 'login' })
  })

  it('ignores routes outside the admin section', () => {
    const to = { matched: [{ meta: {} }] } as unknown as RouteLocationNormalized
    expect(resolveAdminPermissionRedirect(to, state({ isAuthenticated: false }))).toBeNull()
  })
})

describe('/admin parent route (#19833)', () => {
  it('declares the permission on one parent with AdminLayout', () => {
    expect(adminRoutes).toHaveLength(1)
    expect(adminRoutes[0].path).toBe('/admin')
    expect(adminRoutes[0].meta?.permission).toBe('service.management')
    expect(adminRoutes[0].children).toBe(adminChildren)
  })

  it('every old /admin URL still resolves to the same named route and component', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: adminRoutes })
    for (const [path, name] of Object.entries(OLD_ADMIN_PATHS)) {
      const resolved = router.resolve(path)
      expect(resolved.name).toBe(name)
      expect(resolved.matched.map((r) => r.name)).toEqual(['admin', name])
      expect(resolved.meta.admin).toBe(true)
      const record = adminChildren.find((c) => c.name === name)
      expect(String((record as { component: () => unknown }).component)).toContain(OLD_COMPONENT_FILES[name])
    }
  })

  it('is registered in the app router with no leftover top-level /admin/* record', () => {
    expect(routes.filter((r) => r.path === '/admin')).toHaveLength(1)
    expect(routes.filter((r) => r.path.startsWith('/admin/'))).toEqual([])
    const app = createRouter({ history: createMemoryHistory(), routes })
    for (const [path, name] of Object.entries(OLD_ADMIN_PATHS)) {
      expect(app.resolve(path).name).toBe(name)
    }
  })

  it('keeps every child admin-only', () => {
    for (const child of adminChildren.filter((c) => c.name)) {
      expect(child.meta?.admin).toBe(true)
    }
  })
})

describe('AdminLayout nested render (#19833)', () => {
  it('renders the layout header and the matched child inside it', async () => {
    const Child = defineComponent({ render: () => h('div', { class: 'child-page' }, 'child') })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/admin', component: AdminLayout, children: [{ path: 'users', component: Child }] }],
    })
    await router.push('/admin/users')
    const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
    const wrapper = mount(
      defineComponent({ render: () => h('div', [h(RouterView)]) }),
      { global: { plugins: [router, i18n] } },
    )
    await flushPromises()
    expect(wrapper.find('.admin-layout').exists()).toBe(true)
    expect(wrapper.text()).toContain(en.admin.layout.title)
    expect(wrapper.find('.admin-layout .child-page').exists()).toBe(true)
  })
})
