/**
 * Write-ahead reconciliation in the chat store (#14820, #14821).
 *
 * Session state used to be client-authoritative, so two clients could never
 * converge. These tests pin the three reconciliation branches — own echo
 * confirms, foreign message applies, rejection reverts — and assert *which*
 * branch was taken, not merely that the end state happened to match.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '@/stores/useChatStore'
import type { ChatMessage } from '@/types/api'
import apiClient from '@/utils/ApiClient'

vi.mock('@/utils/ApiClient', () => ({
  default: { post: vi.fn(), get: vi.fn() },
}))

function remoteMessage(id: string, content = 'from another client'): ChatMessage {
  return {
    id,
    content,
    sender: 'bot',
    timestamp: new Date(),
  }
}

describe('chat store reconciliation (#14821)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('marks a locally added message as pending', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')

    const id = store.addMessage({ content: 'hello', sender: 'user' })

    expect(id).not.toBeNull()
    expect(store.hasPendingMessages).toBe(true)
  })

  it('confirms a pending message when the server echoes it', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')
    const id = store.addMessage({ content: 'hello', sender: 'user' }) as string

    const confirmed = store.confirmMessage(id)

    expect(confirmed).toBe(true)
    expect(store.hasPendingMessages).toBe(false)
    expect(store.currentMessages).toHaveLength(1)
  })

  it('rewrites the local id to the server id on confirmation', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')
    const localId = store.addMessage({ content: 'hello', sender: 'user' }) as string

    store.confirmMessage(localId, 'server-123')

    expect(store.currentMessages[0].id).toBe('server-123')
  })

  it('reverts the optimistic effect when the server rejects', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')
    const id = store.addMessage({ content: 'nope', sender: 'user' }) as string
    expect(store.currentMessages).toHaveLength(1)

    const rejected = store.rejectMessage(id, 'quota exceeded')

    expect(rejected).toBe(true)
    expect(store.currentMessages).toHaveLength(0)
    expect(store.hasPendingMessages).toBe(false)
  })

  it('confirmMessage reports false for an id it does not hold', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')

    // The distinguishing assertion: a foreign message must NOT be swallowed as
    // a confirmation, or the caller would never apply it as new content.
    expect(store.confirmMessage('never-seen')).toBe(false)
  })

  it('applies a message that originated on another client', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')

    const applied = store.applyRemoteMessage('s1', remoteMessage('remote-1'))

    expect(applied).toBe(true)
    expect(store.currentMessages).toHaveLength(1)
    expect(store.currentMessages[0].content).toBe('from another client')
  })

  it('does not duplicate a remote message it already holds', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')
    store.applyRemoteMessage('s1', remoteMessage('remote-1'))

    const applied = store.applyRemoteMessage('s1', remoteMessage('remote-1'))

    expect(applied).toBe(false)
    expect(store.currentMessages).toHaveLength(1)
  })

  it('the echo of our own message confirms it instead of duplicating it', () => {
    // The defect this guards: our optimistic copy has a local id, the echo has
    // the server's, so an id-only check misses and renders a second bubble.
    const store = useChatStore()
    store.createNewSession('Test', 's1')
    const localId = store.addMessage({ content: 'hello there', sender: 'user' }) as string

    const echo: ChatMessage = {
      id: 'server-echo-1',
      content: 'hello there',
      sender: 'user',
      timestamp: new Date(),
    }
    const applied = store.applyRemoteMessage('s1', echo)

    expect(applied).toBe(false)
    expect(store.currentMessages).toHaveLength(1)
    expect(store.currentMessages[0].id).toBe('server-echo-1')
    expect(store.hasPendingMessages).toBe(false)
    expect(localId).not.toBe('server-echo-1')
  })

  it('a genuinely different message from another client is still applied', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')
    store.addMessage({ content: 'mine', sender: 'user' })

    const applied = store.applyRemoteMessage('s1', remoteMessage('other-1', 'theirs'))

    expect(applied).toBe(true)
    expect(store.currentMessages).toHaveLength(2)
    expect(store.hasPendingMessages).toBe(true)
  })

  it('server snapshot replaces local contents and clears stale pendings', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')
    store.addMessage({ content: 'local only', sender: 'user' })
    expect(store.hasPendingMessages).toBe(true)

    store.applyServerSnapshot('s1', [remoteMessage('srv-1', 'authoritative')])

    expect(store.currentMessages).toHaveLength(1)
    expect(store.currentMessages[0].id).toBe('srv-1')
    expect(store.hasPendingMessages).toBe(false)
  })

  it('a pending message present in the snapshot stays confirmed, not dropped twice', () => {
    const store = useChatStore()
    store.createNewSession('Test', 's1')
    const id = store.addMessage({ content: 'kept', sender: 'user' }) as string

    store.applyServerSnapshot('s1', [remoteMessage(id, 'kept')])

    expect(store.currentMessages).toHaveLength(1)
    expect(store.hasPendingMessages).toBe(false)
  })
})


describe('server-authoritative session creation (#14820)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('adopts the id the server assigns', async () => {
    // The whole point of #14820: the backend owns session identity. Two clients
    // minting their own ids can never converge.
    vi.mocked(apiClient.post).mockResolvedValue({ data: { session_id: 'srv-abc' } })
    const store = useChatStore()

    const result = await store.createServerSession('My chat')

    expect(result).toEqual({ id: 'srv-abc', authoritative: true })
    expect(store.currentSessionId).toBe('srv-abc')
  })

  it('accepts `id` as well as `session_id`', async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ data: { id: 'srv-xyz' } })
    const store = useChatStore()

    const result = await store.createServerSession()

    expect(result.id).toBe('srv-xyz')
    expect(result.authoritative).toBe(true)
  })

  it('falls back to a local session when the backend is unreachable', async () => {
    vi.mocked(apiClient.post).mockRejectedValue(new Error('network down'))
    const store = useChatStore()

    const result = await store.createServerSession('Offline chat')

    // Usable offline — but flagged, so a caller can tell this session is NOT
    // synchronized to other clients rather than assuming it is.
    expect(result.authoritative).toBe(false)
    expect(result.id).toBeTruthy()
    expect(store.sessionCount).toBe(1)
  })

  it('falls back when the response carries no id at all', async () => {
    // A 200 with an unexpected body must not be mistaken for success — that
    // would leave the client believing a server session exists when none does.
    vi.mocked(apiClient.post).mockResolvedValue({ data: {} })
    const store = useChatStore()

    const result = await store.createServerSession()

    expect(result.authoritative).toBe(false)
  })
})
