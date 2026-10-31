// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// #20068: a panel response for an item that is no longer shown changes nothing, a failure from the old
// item does not show on the new one, the new item fetches for itself, and a posted comment keeps the
// thread in order.

import { describe, it, expect, vi } from 'vitest'
import { nextTick, ref } from 'vue'

vi.mock('@/utils/debugUtils', () => ({ createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }) }))

import { useWorkItemPanels } from '../useWorkItemPanels'

const c = (id: string) => ({ id, body: id, author_agent_id: null, author_user_id: 'u', created_at: null })

/** A GET whose responses the test settles by hand, keyed by call order. */
function manualApi() {
  const calls: { url: string; resolve: (v: unknown) => void; reject: (e: Error) => void }[] = []
  const get = vi.fn((url: string) => new Promise((resolve, reject) => calls.push({ url, resolve, reject })))
  return { api: { get } as never, calls, get }
}
const tick = async () => { await nextTick(); await Promise.resolve() }

describe('item changes while a load is in flight', () => {
  it('discards the old first-page response and fetches for the new item', async () => {
    const { api, calls } = manualApi()
    const id = ref('A')
    const p = useWorkItemPanels(api, () => id.value)
    p.fetchComments()
    id.value = 'B'
    await tick()
    expect(calls.map((x) => x.url)).toEqual(['/api/llc/work-items/A/comments', '/api/llc/work-items/B/comments'])
    calls[0].resolve({ comments: [c('a1')], has_more: true })
    await tick()
    expect(p.comments.value).toEqual([])
    expect(p.hasMoreComments.value).toBe(false)
    calls[1].resolve({ comments: [c('b1')], has_more: false })
    await tick()
    expect(p.comments.value.map((x) => x.id)).toEqual(['b1'])
  })

  it('discards an in-flight load-more of the old item and restarts the offset', async () => {
    const { api, calls } = manualApi()
    const id = ref('A')
    const p = useWorkItemPanels(api, () => id.value)
    p.fetchComments()
    calls[0].resolve({ comments: [c('a1'), c('a2')], has_more: true })
    await tick()
    p.fetchComments(true)
    expect(calls[1].url).toBe('/api/llc/work-items/A/comments?offset=2')
    id.value = 'B'
    await tick()
    calls[2].resolve({ comments: [c('b1')], has_more: true })
    await tick()
    calls[1].resolve({ comments: [c('a3')], has_more: true })
    await tick()
    expect(p.comments.value.map((x) => x.id)).toEqual(['b1'])
    p.fetchComments(true)
    expect(calls[3].url).toBe('/api/llc/work-items/B/comments?offset=1')
  })

  it('does not show a failure of the old item on the new one, nor clear the new loading flag', async () => {
    const { api, calls } = manualApi()
    const id = ref('A')
    const p = useWorkItemPanels(api, () => id.value)
    p.fetchActivity()
    id.value = 'B'
    await tick()
    calls[0].reject(new Error('HTTP 500'))
    await tick()
    expect(p.failed.value.activity).toBe(false)
    expect(p.loading.value.activity).toBe(true)
    calls[1].resolve({ items: [] })
    await tick()
    expect(p.loading.value.activity).toBe(false)
  })

  it('clears a failure already showing for the old item, and refetches only requested panels', async () => {
    const { api, calls, get } = manualApi()
    const id = ref('A')
    const p = useWorkItemPanels(api, () => id.value)
    p.fetchArtifacts()
    calls[0].reject(new Error('HTTP 500'))
    await tick()
    expect(p.failed.value.artifacts).toBe(true)
    id.value = 'B'
    await tick()
    expect(p.failed.value.artifacts).toBe(false)
    expect(get).toHaveBeenCalledTimes(2)
    expect(calls[1].url).toBe('/api/llc/work-items/B/products')
  })
})

describe('a posted comment keeps the thread in order', () => {
  it('is appended on the last page', async () => {
    const { api, calls } = manualApi()
    const p = useWorkItemPanels(api, () => 'A')
    p.fetchComments()
    calls[0].resolve({ comments: [c('a1')], has_more: false })
    await tick()
    p.addPostedComment('A', c('new'))
    expect(p.comments.value.map((x) => x.id)).toEqual(['a1', 'new'])
  })

  it('is left out while older pages remain, and appears in order once its page loads', async () => {
    const { api, calls } = manualApi()
    const p = useWorkItemPanels(api, () => 'A')
    p.fetchComments()
    calls[0].resolve({ comments: [c('a1')], has_more: true })
    await tick()
    p.addPostedComment('A', c('new'))
    expect(p.comments.value.map((x) => x.id)).toEqual(['a1'])
    p.fetchComments(true)
    calls[1].resolve({ comments: [c('a2'), c('new')], has_more: false })
    await tick()
    expect(p.comments.value.map((x) => x.id)).toEqual(['a1', 'a2', 'new'])
  })

  it('is ignored when it was posted to an item that is no longer shown', async () => {
    const { api } = manualApi()
    const p = useWorkItemPanels(api, () => 'B')
    p.addPostedComment('A', c('new'))
    expect(p.comments.value).toEqual([])
  })
})
