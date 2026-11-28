// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The scan runner ends with its owner (#21474).
 *
 * A source switch remounts the project page while its page-open run may be on the first cached
 * read. The runner's loop checked only `cancelled`, so the remaining loaders still started, each
 * a request for the source the user had left. Pre-fix: the second scan ran after the dispose.
 */
import { describe, it, expect, vi } from 'vitest'
import { effectScope } from 'vue'

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ info: () => undefined, warn: () => undefined, error: () => undefined, debug: () => undefined }),
}))

import { useAnalyticsScanRunner } from '../useAnalyticsScanRunner'

describe('useAnalyticsScanRunner after its scope is disposed (#21474)', () => {
  it('a page left during the first scan starts none of the remaining scans', async () => {
    let finishFirst!: () => void
    const first = vi.fn(() => new Promise<void>((resolve) => { finishFirst = resolve }))
    const second = vi.fn(async () => {})
    const third = vi.fn(async () => {})
    const scope = effectScope()
    const runner = scope.run(() => useAnalyticsScanRunner())!

    const running = runner.runAll([
      { id: 'stats', label: 'Stats', run: first },
      { id: 'problems', label: 'Problems', run: second },
      { id: 'charts', label: 'Charts', run: third },
    ])
    expect(first).toHaveBeenCalledTimes(1)
    scope.stop()
    finishFirst()
    await running

    expect(second).not.toHaveBeenCalled()
    expect(third).not.toHaveBeenCalled()
    expect(runner.results.value.map((r) => r.status)).toEqual(['completed', 'skipped', 'skipped'])
    expect(runner.running.value).toBe(false)
  })

  it('a disposed runner starts no new run', async () => {
    const scan = vi.fn(async () => {})
    const scope = effectScope()
    const runner = scope.run(() => useAnalyticsScanRunner())!
    scope.stop()

    await runner.runAll([{ id: 'stats', label: 'Stats', run: scan }])

    expect(scan).not.toHaveBeenCalled()
  })

  it('control: a live runner runs every scan', async () => {
    const scans = [vi.fn(async () => {}), vi.fn(async () => {})]
    const scope = effectScope()
    const runner = scope.run(() => useAnalyticsScanRunner())!

    await runner.runAll(scans.map((run, i) => ({ id: `s${i}`, label: `S${i}`, run })))

    expect(scans.map((s) => s.mock.calls.length)).toEqual([1, 1])
    scope.stop()
  })
})
