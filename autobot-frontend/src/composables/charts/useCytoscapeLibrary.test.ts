// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Unit tests for useCytoscapeLibrary.
 *
 * Issue #5206.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useCytoscapeLibrary } from './useCytoscapeLibrary'

// Capture the module-loading surface so tests can simulate success/failure
// without actually pulling in `cytoscape` (which is heavy and has a global
// `use` registry that mutates across tests).
const mockCytoscape = {
  default: vi.fn(() => ({ destroy: vi.fn() })) as unknown as {
    (...args: unknown[]): unknown
    use: (ext: unknown) => void
  },
}
// .use() is a static method on the module
;(mockCytoscape.default as unknown as { use: (ext: unknown) => void }).use = vi.fn()

const mockFcose = { default: { __marker: 'fcose-mock' } }

vi.mock('cytoscape', () => mockCytoscape)
vi.mock('cytoscape-fcose', () => mockFcose)

describe('useCytoscapeLibrary', () => {
  beforeEach(() => {
    vi.mocked(
      (mockCytoscape.default as unknown as { use: (ext: unknown) => void }).use,
    ).mockClear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('loads the library and runs onReady on first ensureReady()', async () => {
    const onReady = vi.fn()
    const { loading, error, cytoscapeModule, ensureReady } =
      useCytoscapeLibrary(onReady)

    expect(loading.value).toBe(false)
    expect(error.value).toBe('')
    expect(cytoscapeModule.value).toBeNull()

    const p = ensureReady()
    expect(loading.value).toBe(true)
    await p

    expect(loading.value).toBe(false)
    expect(error.value).toBe('')
    expect(cytoscapeModule.value).not.toBeNull()
    expect(onReady).toHaveBeenCalledTimes(1)
    // fcose is registered exactly once
    expect(
      (mockCytoscape.default as unknown as { use: (ext: unknown) => void }).use,
    ).toHaveBeenCalledTimes(1)
  })

  it('is idempotent: second ensureReady() skips the import but still runs onReady', async () => {
    const onReady = vi.fn()
    const { ensureReady } = useCytoscapeLibrary(onReady)

    await ensureReady()
    await ensureReady()

    // onReady runs on EVERY ensureReady so callers can re-attach to a
    // possibly-new container — the library load itself is memoized.
    expect(onReady).toHaveBeenCalledTimes(2)
    expect(
      (mockCytoscape.default as unknown as { use: (ext: unknown) => void }).use,
    ).toHaveBeenCalledTimes(1)
  })

  it('populates error and SKIPS onReady when library setup fails', async () => {
    // Simulate a failure at the `cytoscape.use(fcose)` call inside load().
    // This exercises the catch branch without the fragility of re-mocking
    // a dynamic import mid-suite.
    const useSpy = vi.mocked(
      (mockCytoscape.default as unknown as { use: (ext: unknown) => void }).use,
    )
    useSpy.mockImplementationOnce(() => {
      throw new Error('fcose register failed')
    })

    const onReady = vi.fn()
    const { error, cytoscapeModule, ensureReady, loading } =
      useCytoscapeLibrary(onReady)

    await ensureReady()

    expect(loading.value).toBe(false)
    expect(error.value).toContain('Failed to load visualization library')
    expect(error.value).toContain('fcose register failed')
    // The module ref DID get assigned before the use() throw — that's fine,
    // error.value is the gate the consumers watch.
    expect(cytoscapeModule.value).not.toBeNull()
    expect(onReady).not.toHaveBeenCalled()
  })

  it('retry() re-runs ensureReady() fire-and-forget', async () => {
    const onReady = vi.fn()
    const { retry, ensureReady } = useCytoscapeLibrary(onReady)

    // First seed: successful load
    await ensureReady()
    expect(onReady).toHaveBeenCalledTimes(1)

    // Retry: should trigger another ensureReady (which runs onReady again)
    retry()
    // retry is fire-and-forget; yield the microtask queue
    await Promise.resolve()
    await Promise.resolve()
    expect(onReady).toHaveBeenCalledTimes(2)
  })

  it('cytoscapeModule is reactive enough to drive v-if in templates', async () => {
    const { cytoscapeModule, ensureReady } = useCytoscapeLibrary(() => {})
    expect(cytoscapeModule.value).toBeNull()
    await ensureReady()
    // shallowRef triggers reactivity on .value reassignment; that's the
    // contract the composable's consumers rely on.
    expect(cytoscapeModule.value).not.toBeNull()
  })
})
