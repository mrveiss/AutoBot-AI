// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #20631: the SLM is admin only. Every route record carries `meta.admin` except the
 * two a person must reach before being known to be an admin (sign-in and the SSO callback), and every Monitoring
 * tab carries `admin`. The guard then has to send a non-admin somewhere that is not
 * itself flagged, or the navigation loops.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'
import VIEW_SOURCE from '../views/MonitoringView.vue?raw'

const auth = { isAuthenticated: true, isAdmin: false, checkAuth: async () => true }
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/utils/ApiClient', () => ({ default: { get: async () => ({ completed: true }) } }))

import router from './index'

const OPEN_ROUTES = new Set(['/login', '/sso-callback'])

/** Every record in the table, at any depth, written out with its full path. */
function walk(records: readonly RouteRecordRaw[], parent = ''): Array<RouteRecordRaw & { fullPath: string }> {
  return records.flatMap((record) => {
    const fullPath = record.path.startsWith('/') ? record.path : `${parent}/${record.path}`
    return [{ ...record, fullPath }, ...walk(record.children ?? [], fullPath)]
  })
}

function unflagged(records: readonly RouteRecordRaw[]): string[] {
  return walk(records)
    .filter((record) => !OPEN_ROUTES.has(record.fullPath) && record.meta?.admin !== true)
    .map((record) => record.fullPath)
}

function tabsWithoutAdmin(source: string): string[] {
  return (source.match(/^\s*\{ id: '.*$/gm) ?? []).filter((tab) => !tab.includes('admin: true'))
}

describe('the route table (#20631)', () => {
  it('flags every record but login and SSO', () => {
    expect(unflagged(router.options.routes)).toEqual([])
  })

  it('walks the whole table: top level, children and grandchildren', () => {
    const paths = walk(router.options.routes).map((record) => record.fullPath)
    for (const path of ['/fleet/:tab?', '/', '/settings/general', '/tools/vision', '/monitoring/performance/slos']) {
      expect(paths).toContain(path)
    }
    expect(paths.filter((path) => OPEN_ROUTES.has(path)).sort()).toEqual([...OPEN_ROUTES].sort())
  })

  it('control: an unflagged record is reported, at any depth', () => {
    const table: RouteRecordRaw[] = [
      { path: '/login', redirect: '/x' },
      { path: '/plain', redirect: '/x' },
      { path: '/parent', redirect: '/x', meta: { admin: true }, children: [{ path: 'child', redirect: '/x' }] },
    ]
    expect(unflagged(table)).toEqual(['/plain', '/parent/child'])
  })
})

describe('the Monitoring tabs (#20631)', () => {
  it('flags every tab', () => {
    expect(VIEW_SOURCE.match(/^\s*\{ id: '/gm)?.length).toBeGreaterThan(0)
    expect(tabsWithoutAdmin(VIEW_SOURCE)).toEqual([])
  })

  it('control: a tab with no flag is reported', () => {
    expect(tabsWithoutAdmin("  { id: 'a', admin: true },\n  { id: 'b', path: '/b' },\n")).toHaveLength(1)
  })
})

describe('the guard', () => {
  beforeEach(async () => {
    router.getRoutes().forEach((route) => {
      if (route.components) route.components.default = { render: () => null }
    })
    auth.isAuthenticated = true
    auth.isAdmin = false // a non-admin stays on sign-in, so each test starts from the same place
    await router.push('/login')
    auth.isAdmin = true
  })

  it('sends a signed-in non-admin to sign-in with the reason, without looping', async () => {
    auth.isAdmin = false
    await router.push('/fleet/nodes')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.error).toBe('admin_only')
  })

  it('refuses a non-admin a route that used to be open to them', async () => {
    auth.isAdmin = false
    await router.push('/monitoring/performance/overview')
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('control: lets an admin through, and sends a signed-in admin away from sign-in', async () => {
    await router.push('/fleet/nodes')
    expect(router.currentRoute.value.name).toBe('fleet')
    await router.push('/login')
    expect(router.currentRoute.value.name).toBe('fleet')
  })
})
