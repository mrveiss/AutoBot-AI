// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #20644: Batch Processing and Vision are any signed-in user's screens in the user app — signed in,
// not admin-gated, outside /tools (which leaves for the SLM), and reachable from the profile menu.

import { describe, it, expect } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { BATCH_JOBS_PATH, VISION_PATH, userToolRoutes } from '../userToolRoutes'
import { SLM_REDIRECTS, slmRedirectRoutes } from '../slmRedirectRoutes'
import { adminMenuItems, profileMenuItems } from '@/config/navItems'

describe('userToolRoutes (#20644)', () => {
  it('declares both screens for a signed-in user, with no admin gate', () => {
    expect(userToolRoutes.map((r) => r.path)).toEqual([BATCH_JOBS_PATH, VISION_PATH])
    for (const route of userToolRoutes) {
      expect(route.meta?.requiresAuth).toBe(true)
      expect(route.meta?.admin).toBeUndefined()
      expect(route.meta?.hideInNav).toBe(true)
    }
  })

  it('keeps both paths out of every path that leaves for the SLM', () => {
    for (const path of [BATCH_JOBS_PATH, VISION_PATH]) {
      expect(SLM_REDIRECTS.some((r) => path === r.path || (r.deep && path.startsWith(`${r.path}/`)))).toBe(false)
    }
  })

  it('puts both in the profile menu, not the admin menu', () => {
    const profile = profileMenuItems.map((i) => i.to)
    expect(profile).toEqual(expect.arrayContaining([BATCH_JOBS_PATH, VISION_PATH]))
    const admin = adminMenuItems.map((i) => i.to)
    expect(admin).not.toContain(BATCH_JOBS_PATH)
    expect(admin).not.toContain(VISION_PATH)
    expect(profileMenuItems.filter((i) => i.to === BATCH_JOBS_PATH || i.to === VISION_PATH).every((i) => !i.featureFlag)).toBe(
      true,
    )
  })
})

describe('the old SLM paths of the moved screens (#20644)', () => {
  const view = { render: () => null }
  const router = () =>
    createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: BATCH_JOBS_PATH, component: view },
        { path: VISION_PATH, component: view },
        ...slmRedirectRoutes,
      ],
    })

  it.each([
    ['/tools/batch', BATCH_JOBS_PATH],
    ['/tools/vision', VISION_PATH],
  ])('%s stays in this app and lands on %s, not on the /tools wildcard', async (from, to) => {
    const r = router()
    await r.push(from)
    expect(r.currentRoute.value.path).toBe(to)
  })

  it('other /tools paths still match the SLM wildcard', () => {
    const matched = router().resolve('/tools/terminal').matched.map((m) => m.path)
    expect(matched).toEqual(['/tools/:pathMatch(.*)*'])
  })
})
