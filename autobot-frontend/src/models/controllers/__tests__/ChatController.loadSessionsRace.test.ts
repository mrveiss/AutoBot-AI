// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #21997: overlapping session-list loads. The newest load owns the list; a stale response never clears it,
// and `keepOpen` reopens the open chat only when the new list still has it.
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const getChatList = vi.fn()
vi.mock('@/utils/ApiClient', () => ({ default: { invalidateCache: vi.fn() } }))
vi.mock('@/composables/useRequestQueue', () => ({
  requestQueue: { enqueue: vi.fn(({ fn }: { fn: () => unknown }) => fn()) }
}))
vi.mock('@/models/repositories', () => ({
  chatRepository: { getChatList: (...a: unknown[]) => getChatList(...a), getChatMessages: vi.fn() }
}))

import { ChatController } from '../ChatController'
import { useChatStore } from '@/stores/useChatStore'

const entry = (id: string) => ({ id, title: id, messages: [], isActive: false })
const deferred = <T,>() => {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

describe('loadChatSessions sequencing (#21997)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getChatList.mockReset()
  })

  it('drops a first load that resolves after the second, before it clears or imports', async () => {
    const first = deferred<ReturnType<typeof entry>[]>()
    getChatList.mockReturnValueOnce(first.promise).mockResolvedValueOnce([entry('new-company')])
    const controller = new ChatController()
    const store = useChatStore()
    const stale = controller.loadChatSessions()
    await controller.loadChatSessions()
    first.resolve([entry('old-company')])
    await stale
    expect(store.sessions.map((s) => s.id)).toEqual(['new-company'])
  })

  it('reopens the open chat only when the reloaded list still has it', async () => {
    const controller = new ChatController()
    const store = useChatStore()
    store.importSession({ ...entry('keep'), messages: [] })
    store.currentSessionId = 'keep'
    vi.spyOn(controller, 'switchToSession').mockResolvedValue(undefined)
    getChatList.mockResolvedValueOnce([entry('keep'), entry('other')])
    await controller.loadChatSessions(true)
    expect(controller.switchToSession).toHaveBeenCalledWith('keep')
    getChatList.mockResolvedValueOnce([entry('other')])
    store.currentSessionId = 'keep'
    vi.mocked(controller.switchToSession).mockClear()
    await controller.loadChatSessions(true)
    expect(controller.switchToSession).not.toHaveBeenCalled()
  })

  it('discards a list requested under the previous company and reloads for the current one (#16905)', async () => {
    const first = deferred<ReturnType<typeof entry>[]>()
    getChatList.mockReturnValueOnce(first.promise).mockResolvedValueOnce([entry('company-b')])
    const controller = new ChatController()
    const store = useChatStore()
    store.setActiveChatContext({ company_id: 'a' })
    const pending = controller.loadChatSessions()
    store.setActiveChatContext({ company_id: 'b' })
    first.resolve([entry('company-a')])
    await pending
    expect(getChatList.mock.calls.map((c) => c[0])).toEqual(['a', 'b'])
    expect(store.sessions.map((x) => x.id)).toEqual(['company-b'])
  })
})
