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

  it('removes the session when another client deletes it', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    useSessionSync(ref('s1'))
    await settle()
    expect(store.sessionCount).toBe(1)

    harness.__channelHandlers.get('session:s1')!({
      event_type: 'session.deleted',
      payload: { session_id: 's1' },
    })

    expect(store.sessions.find((s) => s.id === 's1')).toBeUndefined()
  })

  it('ignores a session.updated with no title change', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('Original', 's1')
    useSessionSync(ref('s1'))
    await settle()

    harness.__channelHandlers.get('session:s1')!({
      event_type: 'session.updated',
      payload: { changes: {} },
    })

    expect(store.sessions.find((s) => s.id === 's1')?.title).toBe('Original')
  })

  it('ignores an unrecognised event type', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    useSessionSync(ref('s1'))
    await settle()

    harness.__channelHandlers.get('chat:s1')!({ event_type: 'chat.something_new', payload: {} })

    expect(store.currentMessages).toHaveLength(0)
  })

  it('ignores a chat.message_added carrying no message', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    useSessionSync(ref('s1'))
    await settle()

    harness.__channelHandlers.get('chat:s1')!({ event_type: 'chat.message_added', payload: {} })

    expect(store.currentMessages).toHaveLength(0)
  })

  it('a throwing disposer does not prevent the rest of teardown', async () => {
    // Teardown runs on session switch and unmount; one bad disposer must not
    // strand the remaining subscriptions.
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    store.createNewSession('T2', 's2')
    const sessionId = ref<string | null>('s1')

    vi.mocked(liveEventService.subscribe).mockImplementationOnce(() => {
      return () => {
        throw new Error('disposer exploded')
      }
    })

    useSessionSync(sessionId)
    await settle()

    sessionId.value = 's2'
    await settle()

    // Reached the new session despite the failure above.
    expect(harness.__channelHandlers.has('chat:s2')).toBe(true)
  })

  it('accepts message_id when the record carries no id', async () => {
    // Backend records surface their identity on either field depending on the
    // path that produced them.
    vi.mocked(apiClient.get).mockResolvedValue(
      snapshot([{ message_id: 'via-message-id', text: 'hi', sender: 'bot' }])
    )
    const store = useChatStore()
    store.createNewSession('T', 's1')

    useSessionSync(ref('s1'))
    await settle()

    expect(store.currentMessages[0].id).toBe('via-message-id')
  })

  it('defaults a message with no sender to the assistant', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([{ id: 'm1', text: 'hi' }]))
    const store = useChatStore()
    store.createNewSession('T', 's1')

    useSessionSync(ref('s1'))
    await settle()

    expect(store.currentMessages[0].sender).toBe('bot')
  })

  it('defaults missing text to an empty string rather than undefined', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([{ id: 'm1', sender: 'bot' }]))
    const store = useChatStore()
    store.createNewSession('T', 's1')

    useSessionSync(ref('s1'))
    await settle()

    expect(store.currentMessages[0].content).toBe('')
  })

  it('reports a non-Error rejection as a string', async () => {
    // A thrown string would otherwise surface as "undefined" in syncError,
    // which tells the user nothing about why their view is stale.
    vi.mocked(apiClient.get).mockRejectedValue('plain string failure')
    const store = useChatStore()
    store.createNewSession('T', 's1')

    const { syncError } = useSessionSync(ref('s1'))
    await settle()

    expect(syncError.value).toBe('plain string failure')
  })

  it('an event arriving after the session is cleared is a no-op', async () => {
    // Handlers are captured by the subscription, so one can still fire between
    // the session going null and teardown completing.
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    const sessionId = ref<string | null>('s1')
    useSessionSync(sessionId)
    await settle()

    const chatHandler = harness.__channelHandlers.get('chat:s1')!
    const sessionHandler = harness.__channelHandlers.get('session:s1')!
    sessionId.value = null
    await settle()

    chatHandler({
      event_type: 'chat.message_added',
      payload: { message: backendMessage('late', 'too late') },
    })
    sessionHandler({ event_type: 'session.deleted', payload: {} })

    expect(store.sessions.find((s) => s.id === 's1')).toBeDefined()
  })

  it('exposes resync for a caller to trigger a manual rebuild', async () => {
    vi.mocked(apiClient.get).mockResolvedValue(snapshot([]))
    const store = useChatStore()
    store.createNewSession('T', 's1')
    const { resync } = useSessionSync(ref('s1'))
    await settle()

    vi.mocked(apiClient.get).mockResolvedValue(snapshot([backendMessage('m9', 'manual')]))
    await resync('s1')

    expect(store.currentMessages[0].content).toBe('manual')
  })
})
