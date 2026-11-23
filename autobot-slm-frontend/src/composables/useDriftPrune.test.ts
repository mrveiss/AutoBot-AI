// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #22082: the backend refuses a prune request over DRIFT_PRUNE_MAX_PATHS paths
 * (422), so a larger preview is confirmed one batch at a time: the operator
 * confirms exactly the displayed batch, then the next one is re-previewed.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { DRIFT_PRUNE_MAX_PATHS, useDriftPrune } from './useDriftPrune'

const call = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { call: (...args: unknown[]) => call(...args) } }))
vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string, params?: Record<string, unknown>) => `${key}${params ? JSON.stringify(params) : ''}` }),
}))

const filesOf = (from: number, count: number) =>
  Array.from({ length: count }, (_, i) => ({ path: `f${from + i}.py`, detail: null }))

describe('useDriftPrune batching (#22082)', () => {
  beforeEach(() => call.mockReset())

  it('shows and confirms one batch of at most the cap, then re-previews the rest', async () => {
    const total = DRIFT_PRUNE_MAX_PATHS + 7
    const rest = filesOf(DRIFT_PRUNE_MAX_PATHS, 7)
    call
      .mockResolvedValueOnce({ component: 'plugins', files: filesOf(0, total) })
      .mockResolvedValueOnce({ component: 'plugins', removed: [], refused: {}, failed: {} })
      .mockResolvedValueOnce({ component: 'plugins', files: rest })
    const prune = useDriftPrune()

    await prune.preview('plugins')
    const shown = prune.batch('plugins')
    expect(shown.files).toHaveLength(DRIFT_PRUNE_MAX_PATHS)
    expect(shown.total).toBe(total)
    expect(prune.batchNote('plugins')).toContain(`"count":${DRIFT_PRUNE_MAX_PATHS},"total":${total}`)

    await prune.confirm('plugins')
    const sent = call.mock.calls[1][2].body.paths as string[]
    expect(sent).toEqual(shown.files.map((f) => f.path))
    expect(call.mock.calls[2][1]).toBe('/api/code-sync/drift/prune/preview')
    expect(prune.batch('plugins').files.map((f) => f.path)).toEqual(rest.map((f) => f.path))
    expect(prune.batchNote('plugins')).toBeNull()
    expect(prune.results.value.plugins).toBeDefined()
  })

  it('drops the preview when the re-preview finds nothing left', async () => {
    call
      .mockResolvedValueOnce({ component: 'plugins', files: filesOf(0, 2) })
      .mockResolvedValueOnce({ component: 'plugins', removed: ['f0.py', 'f1.py'], refused: {}, failed: {} })
      .mockResolvedValueOnce({ component: 'plugins', files: [] })
    const prune = useDriftPrune()
    await prune.preview('plugins')
    await prune.confirm('plugins')
    expect(prune.previews.value.plugins).toBeUndefined()
  })

  it('reports a failed request through the i18n key', async () => {
    call.mockRejectedValueOnce('boom')
    const prune = useDriftPrune()
    await prune.preview('plugins')
    expect(prune.error.value).toBe('fullTreeDriftPanel.prune.requestFailed')
  })
})
