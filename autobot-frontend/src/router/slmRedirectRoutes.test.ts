// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #20631: the SLM is admin only. The legacy /tools, /monitoring, /settings, /infrastructure
 * paths must reach it only for an admin; the SLM uses web history, so no `/#/` targets.
 * The mini guard below mirrors the three global-guard rules in router/index.ts that these
 * routes lean on (requiresAuth -> login, meta.admin -> /home).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('@/config/ssot-config', () => ({ getSLMAdminUrl: () => 'https://slm.example' }))

import { slmRedirectRoutes } from './slmRedirectRoutes'

const state = { signedIn: true, isAdmin: false }
const hrefSet = vi.fn()
const realLocation = window.location

function makeRouter() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/home', component: { render: () => null } },
      { path: '/login', name: 'login', component: { render: () => null } },
      ...slmRedirectRoutes,
    ],
  })
  router.beforeEach((to) => {
    if (to.matched.some((r) => r.meta.requiresAuth) && !state.signedIn) return { name: 'login' }
    if (to.matched.some((r) => r.meta.admin) && !state.isAdmin) return { path: '/home' }
    return true
  })
  return router
}

beforeEach(() => {
  hrefSet.mockReset()
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: Object.defineProperty({}, 'href', { set: hrefSet, get: () => '' }),
  })
})
afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: realLocation })
})

describe('legacy paths that now live in the SLM', () => {
  const CASES: Array<[string, string]> = [
    ['/tools', 'https://slm.example/tools'],
    ['/tools/terminal', 'https://slm.example/tools'],
    ['/monitoring', 'https://slm.example/monitoring'],
    ['/monitoring/x/y', 'https://slm.example/monitoring'],
    ['/settings', 'https://slm.example/settings'],
    ['/settings/admin/users', 'https://slm.example/settings'],
    ['/infrastructure', 'https://slm.example/infrastructure'],
    ['/tls-certificates', 'https://slm.example/security'],
  ]

  it.each(CASES)('sends an admin from %s to %s', async (from, target) => {
    state.signedIn = true
    state.isAdmin = true
    await makeRouter().push(from)
    expect(hrefSet).toHaveBeenCalledWith(target)
  })

  it.each(CASES)('keeps a non-admin on %s out of the SLM, at /home', async (from) => {
    state.signedIn = true
    state.isAdmin = false
    const router = makeRouter()
    await router.push(from)
    expect(hrefSet).not.toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/home')
  })

  it('sends a signed-out visitor (store not loaded) to login, not the SLM', async () => {
    state.signedIn = false
    state.isAdmin = false
    const router = makeRouter()
    await router.push('/settings')
    expect(hrefSet).not.toHaveBeenCalled()
    expect(router.currentRoute.value.name).toBe('login')
  })

  it('never builds a hash-history target (the SLM uses createWebHistory)', () => {
    const source = readFileSync(join(process.cwd(), 'src/router/slmRedirectRoutes.ts'), 'utf-8')
    const isComment = (l: string) => /^\s*(\*|\/\/|\/\*)/.test(l)
    expect(source.split('\n').filter((l) => !isComment(l)).join('\n')).not.toContain('/#/')
    const index = readFileSync(join(process.cwd(), 'src/router/index.ts'), 'utf-8')
    expect(index).not.toContain('getSLMAdminUrl')
    expect(index).toContain('...slmRedirectRoutes')
  })
})
