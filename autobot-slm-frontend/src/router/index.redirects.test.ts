// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #15224 / #15225 — router redirects for the retired standalone surfaces.
 *
 * #15224: /services was rescued as a direct route by #4762; this reverses
 * that now every capability it had lives in the Orchestration per-node tab.
 * #15225: /replications and /backups/replications both consolidate onto the
 * new Orchestration "replication" tab, which mounts ReplicationView.vue.
 *
 * #15667: this file previously asserted on `router.resolve()`, which runs the
 * matcher ONLY — vue-router applies a record's `redirect` during navigation
 * (`pushWithRedirect`), never in `resolve()`, so a resolved redirect record
 * still reports the source path. Those three assertions could not pass against
 * any router, and nothing noticed because this app's vitest suite ran in no
 * workflow. The redirects themselves were always wired (`src/router/index.ts`
 * `/services`, `/backups/replications`, `/replications`).
 *
 * A real `push()` is used instead, on a router built from the app's own
 * `routes` table with a memory history. That exercises vue-router's redirect
 * handling and the `/orchestration/:tab?` `beforeEnter` for real, while leaving
 * behind the app singleton's global `beforeEach` auth guard — so these
 * assertions still need no authenticated Pinia/auth-store fixture.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { createRouter, createMemoryHistory, type Router } from 'vue-router'
import appRouter from './index'

/** A guard-free clone of the app's route table (redirect records included). */
function createRouteTableUnderTest(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: appRouter.options.routes,
  })
}

describe('router redirects — retired SLM-frontend surfaces (#15224, #15225)', () => {
  let router: Router

  beforeEach(() => {
    router = createRouteTableUnderTest()
  })

  it('/services redirects to the Orchestration per-node tab, not a 404', async () => {
    await router.push('/services')

    expect(router.currentRoute.value.fullPath).toBe('/orchestration/per-node')
    expect(router.currentRoute.value.name).toBe('orchestration')
  })

  it('/replications redirects to the Orchestration replication tab', async () => {
    await router.push('/replications')

    expect(router.currentRoute.value.fullPath).toBe('/orchestration/replication')
    expect(router.currentRoute.value.name).toBe('orchestration')
  })

  it('/backups/replications redirects to the Orchestration replication tab, not the dynamic BackupsView tab route', async () => {
    // The static record must win the match before any redirect is applied. If
    // it ever lost priority to `/backups/:tab?` below it, this would match
    // `backups` with params.tab === 'replications' instead — a silent
    // regression back to a tab that no longer exists.
    const matched = router.resolve('/backups/replications').matched
    expect(matched[matched.length - 1]?.path).toBe('/backups/replications')

    await router.push('/backups/replications')

    expect(router.currentRoute.value.fullPath).toBe('/orchestration/replication')
    expect(router.currentRoute.value.name).not.toBe('backups')
  })

  it('/backups still resolves to BackupsView (unaffected by the replication redirect)', async () => {
    await router.push('/backups')

    expect(router.currentRoute.value.name).toBe('backups')
    expect(router.currentRoute.value.fullPath).toBe('/backups')
  })

  it('/orchestration/replication resolves to the OrchestrationView route', () => {
    const resolved = router.resolve('/orchestration/replication')

    expect(resolved.name).toBe('orchestration')
    expect(resolved.params.tab).toBe('replication')
  })
})
