// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21032: only the latest backlog request writes the list, the spinner and the failure state.

import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'

const get = vi.fn()
vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get }) }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { useBacklogItems } from '../useBacklogItems'

const row = (id: string) => ({ id })

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useBacklogItems request ordering', () => {
  it('keeps the newer list and the spinner when the older response arrives last', async () => {
    const older = deferred<{ items: unknown[] }>()
    const newer = deferred<{ items: unknown[] }>()
    get.mockReset().mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise)
    const company = ref('co1')
    const { items, isLoading, fetchBacklog } = useBacklogItems(company, ref(''))

    const a = fetchBacklog()
    company.value = 'co2'
    const b = fetchBacklog()
    newer.resolve({ items: [row('new')] })
    await b
    expect(isLoading.value).toBe(false)

    const again = deferred<{ items: unknown[] }>()
    get.mockReturnValueOnce(again.promise)
    const c = fetchBacklog() // a third request is in flight while the first one settles
    older.resolve({ items: [row('stale')] })
    await a
    expect(items.value).toEqual([row('new')])
    expect(isLoading.value).toBe(true)
    again.resolve({ items: [row('latest')] })
    await c
    expect(items.value).toEqual([row('latest')])
    expect(isLoading.value).toBe(false)
  })

  it('a superseded failure does not mark the newer load failed', async () => {
    const older = deferred<{ items: unknown[] }>()
    get.mockReset().mockReturnValueOnce(older.promise).mockResolvedValueOnce({ items: [row('ok')] })
    const { items, loadFailed, fetchBacklog } = useBacklogItems(ref('co1'), ref(''))

    const a = fetchBacklog()
    await fetchBacklog()
    older.reject(new Error('down'))
    await a
    expect(loadFailed.value).toBe(false)
    expect(items.value).toEqual([row('ok')])
  })
})

describe('useBacklogItems fetch failure', () => {
  it('reports a failure as its own state, answers false, and a retry clears it', async () => {
    get.mockReset().mockRejectedValueOnce(new Error('down')).mockResolvedValueOnce({ items: [row('a')] })
    const { items, loadFailed, fetchBacklog } = useBacklogItems(ref('co1'), ref(''))

    expect(await fetchBacklog()).toBe(false)
    expect(loadFailed.value).toBe(true)
    expect(items.value).toEqual([])

    expect(await fetchBacklog()).toBe(true)
    expect(loadFailed.value).toBe(false)
    expect(items.value).toEqual([row('a')])
  })

  it('keeps the rows of the same company on a failed refresh, but never another company\'s', async () => {
    get.mockReset().mockResolvedValueOnce({ items: [row('a')] }).mockRejectedValueOnce(new Error('down'))
    const company = ref('co1')
    const { items, loadFailed, fetchBacklog } = useBacklogItems(company, ref(''))
    await fetchBacklog()

    expect(await fetchBacklog()).toBe(false)
    expect(items.value).toEqual([row('a')])
    expect(loadFailed.value).toBe(true)

    company.value = 'co2'
    get.mockRejectedValueOnce(new Error('down'))
    expect(await fetchBacklog()).toBe(false)
    expect(items.value).toEqual([])
  })
})
