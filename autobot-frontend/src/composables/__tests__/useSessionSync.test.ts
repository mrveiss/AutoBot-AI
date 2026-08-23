/**
 * Client-side session synchronization (#14820, #14818).
 *
 * This composable is the seam that makes the backend authoritative for a
 * conversation: subscribe to its channels, apply what the server publishes,
 * recognise our own echoes, and rebuild from the REST snapshot when the server
 * says our view cannot be trusted.
 *
 * The cases that carry real risk are the negative ones — a failed resync must
 * not look like an empty conversation, and our own echo must not render twice.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { ref, nextTick } from 'vue'
import { useSessionSync } from '@/composables/useSessionSync'
import { useChatStore } from '@/stores/useChatStore'
import apiClient from '@/utils/ApiClient'
import liveEventService from '@/services/LiveEventService'

vi.mock('@/utils/ApiClient', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

vi.mock('@/services/LiveEventService', () => {
  const channelHandlers = new Map<string, (e: unknown) => void>()
  const resyncHandlers = new Map<string, (e: unknown) => void>()
  return {
    default: {
      subscribe: vi.fn((channel: string, cb: (e: unknown) => void) => {
        channelHandlers.set(channel, cb)
        return () => channelHandlers.delete(channel)
      }),
      onResync: vi.fn((channel: string, cb: (e: unknown) => void) => {
        resyncHandlers.set(channel, cb)
        return () => resyncHandlers.delete(channel)
      }),
      __channelHandlers: channelHandlers,
      __resyncHandlers: resyncHandlers,
    },
  }
})

type Harness = {
  __channelHandlers: Map<string, (e: unknown) => void>
  __resyncHandlers: Map<string, (e: unknown) => void>
}

const harness = liveEventService as unknown as Harness

function snapshot(messages: Array<Record<string, unknown>>) {
  return { data: { messages } }
}

function backendMessage(id: string, text: string, sender = 'bot') {
  return { id, text, sender, timestamp: '2026-08-23T10:00:00Z', message_type: 'llm_response' }
}

/**
 * Let the watcher and its awaited resync settle.
 *
 * `watch(..., { immediate: true })` runs its callback through Vue's scheduler,
 * and the callback then awaits a mocked HTTP round trip. `nextTick` flushes the
 * scheduler; the macrotask turn drains the promise chain behind it. Hand-rolled
 * microtask counting would work by accident today and break the moment the
 * composable gains another await.
 */
async function settle() {
  await nextTick()
  await new Promise((r) => setTimeout(r, 0))
  await nextTick()
}

describe('useSessionSync (#14820)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    harness.__channelHandlers.clear()
    harness.__resyncHandlers.clear()
  })

  it('subscribes to both the session and chat channels', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')

    useSessionSync(ref('s1'))
    await settle()

    expect(harness.__channelHandlers.has('session:s1')).toBe(true)
    expect(harness.__channelHandlers.has('chat:s1')).toBe(true)
  })

  it('applies the server snapshot on attach', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([backendMessage('m1', 'from server')]))
    const store = useChatStore()
    store.createNewSession('T', 's1')

    const { synchronized } = useSessionSync(ref('s1'))
    await settle()

    expect(synchronized.value).toBe(true)
    expect(store.currentMessages).toHaveLength(1)
    // Backend `text` maps onto the store's canonical `content` field.
    expect(store.currentMessages[0].content).toBe('from server')
  })

  it('reports a failed resync instead of leaving a stale view looking authoritative', async () => {
    // The distinguishing case: a fetch failure and an empty conversation must
    // not be indistinguishable.
    vi.mocked(apiClient.get).mockRejectedValue(new Error('backend down'))
    const store = useChatStore()
    store.createNewSession('T', 's1')

    const { synchronized, syncError } = useSessionSync(ref('s1'))
    await settle()

    expect(synchronized.value).toBe(false)
    expect(syncError.value).toContain('backend down')
  })

  it('reports an unexpected snapshot shape rather than treating it as empty', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data: {} })
    const store = useChatStore()
    store.createNewSession('T', 's1')

    const { synchronized, syncError } = useSessionSync(ref('s1'))
    await settle()

    expect(synchronized.value).toBe(false)
    expect(syncError.value).toBeTruthy()
  })

  it('drops a remote message that carries no usable id', async () => {
    // Without an id it cannot be deduplicated, and appending it blindly is how
    // duplicate bubbles appear.
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([{ text: 'no id here', sender: 'bot' }]))
    const store = useChatStore()
    store.createNewSession('T', 's1')

    useSessionSync(ref('s1'))
    await settle()

    expect(store.currentMessages).toHaveLength(0)
  })

  it('applies a message published by another client', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    useSessionSync(ref('s1'))
    await settle()

    harness.__channelHandlers.get('chat:s1')!({
      event_type: 'chat.message_added',
      payload: { message: backendMessage('remote-1', 'from another tab') },
    })

    expect(store.currentMessages).toHaveLength(1)
    expect(store.currentMessages[0].content).toBe('from another tab')
  })

  it('clears the conversation on chat.cleared', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([backendMessage('m1', 'existing')]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    useSessionSync(ref('s1'))
    await settle()
    expect(store.currentMessages).toHaveLength(1)

    harness.__channelHandlers.get('chat:s1')!({ event_type: 'chat.cleared', payload: {} })

    expect(store.currentMessages).toHaveLength(0)
  })

  it('renames the session on session.updated', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('Old name', 's1')
    useSessionSync(ref('s1'))
    await settle()

    harness.__channelHandlers.get('session:s1')!({
      event_type: 'session.updated',
      payload: { changes: { title: 'Renamed elsewhere' } },
    })

    expect(store.sessions.find((s) => s.id === 's1')?.title).toBe('Renamed elsewhere')
  })

  it('rebuilds from the snapshot when the server sends a resync directive', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    useSessionSync(ref('s1'))
    await settle()

    vi.mocked(apiClient.get).mockResolvedValue(snapshot([backendMessage('after', 'rebuilt')]))
    harness.__resyncHandlers.get('chat:s1')!({ channel: 'chat:s1', reason: 'gap_exceeds_retention' })
    await settle()

    expect(store.currentMessages).toHaveLength(1)
    expect(store.currentMessages[0].content).toBe('rebuilt')
  })

  it('tears down subscriptions when the session id becomes null', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    const sessionId = ref<string | null>('s1')
    useSessionSync(sessionId)
    await settle()
    expect(harness.__channelHandlers.has('chat:s1')).toBe(true)

    sessionId.value = null
    await settle()

    expect(harness.__channelHandlers.has('chat:s1')).toBe(false)
  })

  it('re-subscribes to the new channels when the session changes', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('A', 's1')
    store.createNewSession('B', 's2')
    const sessionId = ref<string | null>('s1')
    useSessionSync(sessionId)
    await settle()

    sessionId.value = 's2'
    await settle()

    expect(harness.__channelHandlers.has('chat:s2')).toBe(true)
    expect(harness.__channelHandlers.has('chat:s1')).toBe(false)
  })
})
