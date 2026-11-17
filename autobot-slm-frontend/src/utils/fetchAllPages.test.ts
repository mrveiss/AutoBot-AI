// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21584: the node list answers one page (default 20, at most 100); every caller must get the whole fleet
// through one fetch, with no request above the ceiling and a visible signal when a page could not be read.

import { describe, it, expect, vi } from 'vitest'
import { fetchAllPages, MAX_PAGE_SIZE, PartialListError } from './fetchAllPages'
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
