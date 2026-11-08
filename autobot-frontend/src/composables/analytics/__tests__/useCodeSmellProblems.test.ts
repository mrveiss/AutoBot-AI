// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const load = vi.fn(async () => undefined)
let captured: { onError?: () => void; onSuccess?: (d: unknown[]) => void } = {}

vi.mock('@/composables/api/useFetchEndpoint', () => ({
  useFetchEndpoint: (opts: typeof captured) => {
    captured = opts
    return { load, error: ref(''), loading: ref(false), data: ref(null) }
  },
}))

import { useCodeSmellProblems } from '../useCodeSmellProblems'

describe('useCodeSmellProblems category wiring (#20493)', () => {
  beforeEach(() => load.mockClear())

  it('loads production code by default, sending file_category', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.loadSmellProblems()
    expect(load).toHaveBeenCalledWith({ file_category: 'code' })
  })

  it('selecting a category reloads with that category', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.selectSmellCategory('test')
    expect(s.smellCategory.value).toBe('test')
    expect(load).toHaveBeenCalledWith({ file_category: 'test' })
  })

  it('the all category sends no file_category', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.selectSmellCategory('all')
    expect(load).toHaveBeenCalledWith(undefined)
  })

  it('a failed load clears the previous findings', () => {
    const s = useCodeSmellProblems((u) => u)
    captured.onSuccess?.([{ type: 'long_function', severity: 'high', message: 'm', file_path: 'a.py' }])
    expect(s.smellsForPanel.value).toHaveLength(1)
    captured.onError?.()
    expect(s.smellsForPanel.value).toHaveLength(0)
  })

  it('the export is the panel list under the selected category', async () => {
    const s = useCodeSmellProblems((u) => u)
    captured.onSuccess?.([{ type: 'long_function', severity: 'high', message: 'm', file_path: 'a.py' }])
    await s.selectSmellCategory('test')
    expect(s.smellsExport.value.file_category).toBe('test')
    expect(s.smellsExport.value.summary.total_smells).toBe(s.smellsForPanel.value.length)
  })
})
