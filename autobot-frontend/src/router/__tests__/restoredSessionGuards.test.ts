// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #19833: the real router.beforeEach, driven with a session that exists only on
// the backend (nothing in storage, so `checkAuthFromBackend()` restores it). The
// permission, role and onboarding gates must still run on that restored session;
// a bare `return` after the restore skipped all of them (fail open).

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const meResponse = vi.hoisted(() => ({ role: 'operator', presetApplied: true }))

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get: vi.fn().mockResolvedValue([]) }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))
vi.mock('@/utils/fetchWithAuth', () => ({
  getAuthToken: () => null,
  fetchWithAuth: vi.fn(async (url: string) => {
    const body = String(url).endsWith('/auth/me')
      ? { authenticated: true, username: 'restored', role: meResponse.role }
      : { preset_applied: meResponse.presetApplied }
    return { ok: true, json: async () => body }
  }),
}))

import router from '@/router'
import { fetchWithAuth } from '@/utils/fetchWithAuth'

async function visitAs(role: string, path: string, presetApplied = true): Promise<string> {
  meResponse.role = role
  meResponse.presetApplied = presetApplied
  await router.push('/login').catch(() => undefined)
  await router.push(path).catch(() => undefined)
  return router.currentRoute.value.path
}

// Cold lazy-component imports of the real route table can exceed the 10s default.
describe('router.beforeEach on a session restored from the backend (#19833)', { timeout: 60_000 }, () => {
  beforeEach(async () => {
    localStorage.clear()
    sessionStorage.clear()
    setActivePinia(createPinia())
    vi.mocked(fetchWithAuth).mockClear()
  })

  it('denies a non-admin restored session an meta.admin route', async () => {
    expect(await visitAs('operator', '/admin/users')).toBe('/home')
  })

  it('lets an administrative restored session reach the same route', async () => {
    expect(await visitAs('admin', '/admin/users')).toBe('/admin/users')
  })

  it('redirects a restored session with onboarding pending to /onboarding', async () => {
    expect(await visitAs('admin', '/chat', false)).toBe('/onboarding')
  })

  it('does not trap a restored session on /onboarding or loop', async () => {
    expect(await visitAs('admin', '/onboarding', false)).toBe('/onboarding')
    const statusCalls = vi.mocked(fetchWithAuth).mock.calls.filter(([u]) =>
      String(u).includes('/api/onboarding/status'),
    )
    expect(statusCalls.length).toBeLessThanOrEqual(1)
  })
})
