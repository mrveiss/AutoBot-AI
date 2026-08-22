/**
 * Write-ahead reconciliation in the chat store (#14820, #14821).
 *
 * Session state used to be client-authoritative, so two clients could never
 * converge. These tests pin the three reconciliation branches — own echo
 * confirms, foreign message applies, rejection reverts — and assert *which*
 * branch was taken, not merely that the end state happened to match.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '@/stores/useChatStore'
import type { ChatMessage } from '@/types/api'

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
