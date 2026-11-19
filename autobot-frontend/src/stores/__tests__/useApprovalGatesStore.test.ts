// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #20917: the approvals waiting for the person are fetched once and refetched on a live event.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { flushPromises } from '@vue/test-utils'

const get = vi.fn()
const post = vi.fn()
type Handler = (event: { event_type: string }) => void
const live = vi.hoisted(() => ({ handler: null as Handler | null, unsubscribe: vi.fn() }))
const subscribe = vi.hoisted(() =>
  vi.fn((_channel: string, cb: Handler) => {
    live.handler = cb
    return live.unsubscribe
  }),
)

vi.mock('@/plugins/api', () => ({ useApiClient: () => ({ get, post }) }))
vi.mock('@/services/LiveEventService', () => ({ default: { subscribe } }))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import { useApprovalGatesStore } from '../useApprovalGatesStore'

const ROW = { id: 'a1', title: 'Workflow step waiting for approval', approval_type: 'workflow_gate', source: 'workflow_step' }

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset().mockResolvedValue([ROW])
  post.mockReset().mockResolvedValue({})
  subscribe.mockClear()
  live.unsubscribe.mockClear()
  live.handler = null
})

describe('useApprovalGatesStore (#20917)', () => {
  it('start reads the pending list and subscribes to the global channel once', async () => {
    const store = useApprovalGatesStore()
    await store.start()
    await store.start()
    expect(get).toHaveBeenCalledWith('/api/approval-gates/pending')
    expect(store.count).toBe(1)
    expect(subscribe).toHaveBeenCalledTimes(1)
    expect(subscribe.mock.calls[0][0]).toBe('global')
  })

  it.each(['approval_pending', 'approval_approved', 'approval_rejected', 'approval_withdrawn', 'approval_expired'])(
    'refetches on %s',
    async (eventType) => {
      const store = useApprovalGatesStore()
      await store.start()
      get.mockClear()
      get.mockResolvedValue([])
      live.handler!({ event_type: eventType })
      await flushPromises()
      expect(get).toHaveBeenCalledTimes(1)
      expect(store.count).toBe(0)
    },
  )

  it('does not refetch for an unrelated event (control)', async () => {
    await useApprovalGatesStore().start()
    get.mockClear()
    live.handler!({ event_type: 'provider_fallback' })
    await flushPromises()
    expect(get).not.toHaveBeenCalled()
  })

  it('decide posts to the existing route and then refetches', async () => {
    const store = useApprovalGatesStore()
    await store.start()
    get.mockClear()
    expect(await store.decide('a1', 'reject')).toBe(true)
    expect(post).toHaveBeenCalledWith('/api/approval-gates/a1/reject', {})
    expect(get).toHaveBeenCalledTimes(1)
    expect(store.deciding.size).toBe(0)
  })

  it('a refused decision reports false and does not refetch (control)', async () => {
    const store = useApprovalGatesStore()
    await store.start()
    get.mockClear()
    post.mockRejectedValue(new Error('403'))
    expect(await store.decide('a1', 'approve')).toBe(false)
    expect(get).not.toHaveBeenCalled()
  })

  it('stop unsubscribes and clears the list', async () => {
    const store = useApprovalGatesStore()
    await store.start()
    store.stop()
    expect(live.unsubscribe).toHaveBeenCalled()
    expect(store.count).toBe(0)
  })
})
