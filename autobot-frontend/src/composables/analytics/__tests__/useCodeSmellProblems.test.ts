// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const load = vi.fn(async (..._args: unknown[]) => undefined)
type Ctx = { category: string; seq: number }
let captured: {
  onError?: (message: string, err: unknown, ctx: Ctx) => void
  onSuccess?: (d: unknown[], raw: unknown, ctx: Ctx) => void
} = {}
const ROW = { type: 'long_function', severity: 'high', message: 'm', file_path: 'a.py' }
/** The per-request context the n-th load was given (the last one by default). */
const ctxOf = (n = load.mock.calls.length - 1) => load.mock.calls[n][1] as Ctx
const succeed = (rows: unknown[], n?: number) => captured.onSuccess?.(rows, {}, ctxOf(n))
const fail = (n?: number) => captured.onError?.('boom', new Error('boom'), ctxOf(n))

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

  it('a failed load clears the previous findings', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.loadSmellProblems()
    succeed([ROW])
    expect(s.smellsForPanel.value).toHaveLength(1)
    fail()
    expect(s.smellsForPanel.value).toHaveLength(0)
  })

  it('the export is the panel list under the category the rows were loaded for', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.selectSmellCategory('test')
    succeed([ROW])
    expect(s.smellsExport.value.file_category).toBe('test')
    expect(s.smellsExport.value.summary.total_smells).toBe(s.smellsForPanel.value.length)
  })

  it('an export taken mid-load keeps the old rows labelled with their own category', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.loadSmellProblems()
    succeed([ROW])
    await s.selectSmellCategory('test') // load resolves without onSuccess: still in flight
    expect(s.smellCategory.value).toBe('test')
    expect(s.smellsExport.value.file_category).toBe('code')
  })

  it('counts code_smell_<pattern> findings in the cards and the export', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.loadSmellProblems()
    succeed([
      { type: 'code_smell_god_class', severity: 'high', message: 'm', file_path: 'a.py' },
      { type: 'unrelated_type', severity: 'high', message: 'm', file_path: 'b.py' },
    ])
    expect(s.smellsForPanel.value).toHaveLength(1)
    expect(s.smellsExport.value.summary.total_smells).toBe(1)
    expect(s.smellsExport.value.smells[0].smell_type).toBe('code_smell_god_class')
  })

  it('resetSmells empties the rows', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.loadSmellProblems()
    succeed([ROW])
    s.resetSmells()
    expect(s.smellsForPanel.value).toHaveLength(0)
  })
})

// #21784: a refresh that fires while the same category is loading must not cancel it, and a
// superseded response must not label rows with the newer category.
describe('useCodeSmellProblems request handling (#21784)', () => {
  beforeEach(() => {
    load.mockReset()
    load.mockImplementation(async () => undefined)
  })

  const slowLoad = () => {
    let finish: () => void = () => {}
    load.mockImplementationOnce(() => new Promise<undefined>((resolve) => { finish = () => resolve(undefined) }))
    return () => finish()
  }

  it('a refresh during a slow load of the same category reuses the request', async () => {
    const finish = slowLoad()
    const s = useCodeSmellProblems((u) => u)
    const first = s.loadSmellProblems()
    const second = s.loadSmellProblems() // the real-time refresh tick
    expect(load).toHaveBeenCalledTimes(1)
    finish()
    await Promise.all([first, second])
    await s.loadSmellProblems() // finished: the next tick starts a new request
    expect(load).toHaveBeenCalledTimes(2)
  })

  it('a different category starts its own request', async () => {
    slowLoad()
    const s = useCodeSmellProblems((u) => u)
    void s.loadSmellProblems()
    await s.selectSmellCategory('test')
    expect(load).toHaveBeenCalledTimes(2)
    expect(load.mock.calls[1][0]).toEqual({ file_category: 'test' })
  })

  it('a superseded response is ignored: the newer category keeps its own rows and label', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.loadSmellProblems() // request 0: code
    await s.selectSmellCategory('test') // request 1: test, supersedes it
    succeed([{ ...ROW, file_path: 'stale.py' }], 0) // the code response arrives late
    expect(s.smellsForPanel.value).toHaveLength(0)
    expect(s.smellsStale.value).toBe(true)
    succeed([ROW], 1)
    expect(s.smellsForPanel.value).toHaveLength(1)
    expect(s.smellsExport.value.file_category).toBe('test')
    expect(s.smellsStale.value).toBe(false)
  })

  it('a superseded failure does not clear the newer rows', async () => {
    const s = useCodeSmellProblems((u) => u)
    await s.loadSmellProblems()
    await s.selectSmellCategory('test')
    succeed([ROW], 1)
    fail(0)
    expect(s.smellsForPanel.value).toHaveLength(1)
  })
})
