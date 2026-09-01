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
 * `router.resolve()` runs the matcher (including static redirect
 * resolution) without executing navigation guards, so these assertions
 * exercise the actual route table without needing an authenticated
 * Pinia/auth-store fixture.
 */

import { describe, it, expect } from 'vitest'
import router from './index'

describe('router redirects — retired SLM-frontend surfaces (#15224, #15225)', () => {
  it('/services redirects to the Orchestration per-node tab, not a 404', () => {
    const resolved = router.resolve('/services')

    expect(resolved.fullPath).toBe('/orchestration/per-node')
  })

  it('/replications redirects to the Orchestration replication tab', () => {
    const resolved = router.resolve('/replications')

    expect(resolved.fullPath).toBe('/orchestration/replication')
  })

  it('/backups/replications redirects to the Orchestration replication tab, not the dynamic BackupsView tab route', () => {
    const resolved = router.resolve('/backups/replications')

    expect(resolved.fullPath).toBe('/orchestration/replication')
    // If the static route above ever lost priority over `/backups/:tab?`,
    // this would resolve to `backups` with params.tab === 'replications'
    // instead — a silent regression back to a tab that no longer exists.
    expect(resolved.name).not.toBe('backups')
  })

  it('/backups still resolves to BackupsView (unaffected by the replication redirect)', () => {
    const resolved = router.resolve('/backups')

    expect(resolved.name).toBe('backups')
  })

  it('/orchestration/replication resolves to the OrchestrationView route', () => {
    const resolved = router.resolve('/orchestration/replication')

    expect(resolved.name).toBe('orchestration')
    expect(resolved.params.tab).toBe('replication')
  })
})
