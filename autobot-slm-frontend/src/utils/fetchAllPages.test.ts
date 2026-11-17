// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21584: the node list answers one page (default 20, at most 100); every caller must get the whole fleet
// through one fetch, with no request above the ceiling and a visible signal when a page could not be read.

import { describe, it, expect, vi } from 'vitest'
import { fetchAllPages, MAX_PAGE_SIZE, MAX_PAGES, PartialListError } from './fetchAllPages'
import type { PageParams } from './fetchAllPages'

/** A server holding `total` rows, answering any page window, recording every request. */
function server(total: number, failOnPage?: number) {
  const rows = Array.from({ length: total }, (_, i) => `node-${i + 1}`)
  const requests: PageParams[] = []
  const getPage = vi.fn(async (params: PageParams) => {
    requests.push(params)
    if (params.page === failOnPage) throw new Error('504 gateway timeout')
    const start = (params.page - 1) * params.per_page
    return { items: rows.slice(start, start + params.per_page), total }
  })
  return { rows, requests, getPage }
}

describe('fetchAllPages (#21584)', () => {
  it('a fleet larger than one page is read in full, in order', async () => {
    const s = server(250)
    const all = await fetchAllPages(s.getPage)
    expect(all).toEqual(s.rows)
    expect(s.requests.map((r) => r.page)).toEqual([1, 2, 3])
  })

  it('never asks for more than the backend ceiling in one request', async () => {
    const s = server(250)
    await fetchAllPages(s.getPage, 5000)
    expect(s.requests.every((r) => r.per_page <= MAX_PAGE_SIZE)).toBe(true)
    expect(MAX_PAGE_SIZE).toBe(100)
  })

  it('a fleet of exactly one page is one request; an empty fleet is one request', async () => {
    const full = server(MAX_PAGE_SIZE)
    expect(await fetchAllPages(full.getPage)).toHaveLength(MAX_PAGE_SIZE)
    expect(full.requests).toHaveLength(1)
    const none = server(0)
    expect(await fetchAllPages(none.getPage)).toEqual([])
    expect(none.requests).toHaveLength(1)
  })

  it('a later page that fails throws PartialListError carrying what was read and the total', async () => {
    const s = server(250, 2)
    const err = await fetchAllPages(s.getPage).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(PartialListError)
    const partial = err as PartialListError<string>
    expect(partial.items).toEqual(s.rows.slice(0, MAX_PAGE_SIZE))
    expect(partial.total).toBe(250)
    expect(partial.message).toContain('Loaded 100 of 250')
    expect(partial.message).toContain('504 gateway timeout')
  })

  it('a first page that fails is rethrown as it is: nothing was read', async () => {
    const s = server(250, 1)
    await expect(fetchAllPages(s.getPage)).rejects.toThrow('504 gateway timeout')
    await expect(fetchAllPages(s.getPage)).rejects.not.toBeInstanceOf(PartialListError)
  })

  it('rows removed while paging end the loop instead of asking for ever', async () => {
    let calls = 0
    const getPage = vi.fn(async ({ page }: PageParams) => {
      calls += 1
      return page === 1 ? { items: ['a', 'b'], total: 5 } : { items: [], total: 2 }
    })
    expect(await fetchAllPages(getPage, 2)).toEqual(['a', 'b'])
    expect(calls).toBe(2)
  })
})

describe('fetchAllPages with no usable total (#21584)', () => {
  /** A server whose responses carry the given `total` value, whatever it is. */
  function noTotal(rowCount: number, total: unknown) {
    const rows = Array.from({ length: rowCount }, (_, i) => i + 1)
    const requests: PageParams[] = []
    const getPage = async (params: PageParams) => {
      requests.push(params)
      const start = (params.page - 1) * params.per_page
      return { items: rows.slice(start, start + params.per_page), total: total as number }
    }
    return { rows, requests, getPage }
  }

  it.each([undefined, Number.NaN, Number.POSITIVE_INFINITY, null])('a total of %s does not stop after page 1', async (total) => {
    const s = noTotal(250, total)
    expect(await fetchAllPages(s.getPage)).toEqual(s.rows)
    expect(s.requests.map((r) => r.page)).toEqual([1, 2, 3])
    expect(s.requests.every((r) => r.per_page <= MAX_PAGE_SIZE)).toBe(true)
  })

  it('an unknown total with an exact multiple of the page size ends on the empty page', async () => {
    const s = noTotal(200, undefined)
    expect(await fetchAllPages(s.getPage)).toHaveLength(200)
    expect(s.requests).toHaveLength(3)
  })

  it('a server that never stops answering is cut off by the page guard', async () => {
    const getPage = vi.fn(async () => ({ items: [1], total: undefined as unknown as number }))
    const all = await fetchAllPages(getPage, 1)
    expect(all).toHaveLength(MAX_PAGES)
    expect(getPage).toHaveBeenCalledTimes(MAX_PAGES)
  })

  it('a later page that fails with an unknown total still reports what was read', async () => {
    let n = 0
    const getPage = async () => {
      if (++n === 2) throw new Error('504')
      return { items: Array.from({ length: 100 }, (_, i) => i), total: undefined as unknown as number }
    }
    const err = (await fetchAllPages(getPage).catch((e: unknown) => e)) as PartialListError<number>
    expect(err).toBeInstanceOf(PartialListError)
    expect(err.items).toHaveLength(100)
    expect(err.total).toBeNull()
  })

  it('a server that ignores `page` and has no total ends on the repeated first id', async () => {
    const getPage = vi.fn(async () => ({ items: Array.from({ length: 100 }, (_, i) => ({ id: i })), total: undefined as unknown as number }))
    const all = await fetchAllPages(getPage, 100, (row) => row.id)
    expect(all).toHaveLength(100)
    expect(getPage).toHaveBeenCalledTimes(2)
  })

  it('without an id reader the runaway guard still ends it, at 50 pages', async () => {
    const getPage = vi.fn(async () => ({ items: [1], total: undefined as unknown as number }))
    expect(await fetchAllPages(getPage, 1)).toHaveLength(MAX_PAGES)
    expect(MAX_PAGES).toBe(50)
  })
})
