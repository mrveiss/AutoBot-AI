// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
import { describe, it, expect, beforeEach } from 'vitest'
import { effectScope, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useChatStore } from '@/stores/useChatStore'
import { KNOWLEDGE_STORAGE_KEY, MAX_REMEMBERED_SESSIONS, expectDraftAdoption, resetChatKnowledgeState, useChatKnowledge } from '../useChatKnowledge'

beforeEach(() => {
  setActivePinia(createPinia())
  resetChatKnowledgeState()
})

describe('useChatKnowledge', () => {
  it('is on by default, as the composer toggle was', () => {
    expect(useChatKnowledge().enabled.value).toBe(true)
  })

  it('shares one source between the composer and the header for the current chat', () => {
    const composer = useChatKnowledge()
    const header = useChatKnowledge()
    composer.enabled.value = false
    expect(header.enabled.value).toBe(false)
  })

  it('switching sessions shows each session its own state, and a new chat starts on', () => {
    const store = useChatStore()
    const a = store.createNewSession('A', 'session-a')
    const { enabled } = useChatKnowledge()
    enabled.value = false
    const b = store.createNewSession('B', 'session-b')
    expect(store.currentSessionId).toBe(b)
    expect(enabled.value).toBe(true) // turning it off in A did not carry into B
    store.switchToSession(a)
    expect(enabled.value).toBe(false)
    store.switchToSession(b)
    expect(enabled.value).toBe(true)
  })

  it('persists per session in this browser, and survives a reload of the module state', () => {
    const store = useChatStore()
    const id = store.createNewSession('A', 'session-a')
    useChatKnowledge().enabled.value = false
    expect(JSON.parse(localStorage.getItem(KNOWLEDGE_STORAGE_KEY)!)).toEqual({ [id]: false })
  })

  it('bounds what it remembers, dropping the oldest choice first', () => {
    const store = useChatStore()
    const { enabled } = useChatKnowledge()
    for (let i = 0; i <= MAX_REMEMBERED_SESSIONS; i++) {
      store.createNewSession(`S${i}`, `s-${i}`)
      enabled.value = false
    }
    const saved = JSON.parse(localStorage.getItem(KNOWLEDGE_STORAGE_KEY)!)
    expect(Object.keys(saved)).toHaveLength(MAX_REMEMBERED_SESSIONS)
    expect(saved['s-0']).toBeUndefined()
  })

  it('a choice made before the first message moves to the session that message creates', async () => {
    const store = useChatStore()
    store.currentSessionId = null
    const { enabled } = useChatKnowledge()
    enabled.value = false
    expectDraftAdoption() // the composer's send marks the session it is about to create
    store.createNewSession('First', 'session-first')
    await nextTick()
    expect(enabled.value).toBe(false)
    expect(JSON.parse(localStorage.getItem(KNOWLEDGE_STORAGE_KEY)!)['session-first']).toBe(false)
  })

  it('a draft choice does not leak onto an existing chat opened afterwards', async () => {
    const store = useChatStore()
    const existing = store.createNewSession('Old', 'session-old')
    store.currentSessionId = null
    const { enabled } = useChatKnowledge()
    enabled.value = false // toggled with no chat open, and no send follows
    store.switchToSession(existing)
    await nextTick()
    expect(enabled.value).toBe(true) // the default, not the draft
    expect(JSON.parse(localStorage.getItem(KNOWLEDGE_STORAGE_KEY)!)).toEqual({})
  })

  it('re-reads the map another tab stored, and stops listening when its scope ends', async () => {
    const store = useChatStore()
    const id = store.createNewSession('A', 'session-a')
    const scope = effectScope()
    const { enabled } = scope.run(() => useChatKnowledge())!
    expect(enabled.value).toBe(true)
    const fromOtherTab = (): void => {
      localStorage.setItem(KNOWLEDGE_STORAGE_KEY, JSON.stringify({ [id]: false }))
      window.dispatchEvent(new StorageEvent('storage', { key: KNOWLEDGE_STORAGE_KEY }))
    }
    fromOtherTab()
    expect(enabled.value).toBe(false)
    scope.stop()
    localStorage.setItem(KNOWLEDGE_STORAGE_KEY, JSON.stringify({ [id]: true }))
    window.dispatchEvent(new StorageEvent('storage', { key: KNOWLEDGE_STORAGE_KEY }))
    expect(enabled.value).toBe(false) // no longer synced
  })
})
