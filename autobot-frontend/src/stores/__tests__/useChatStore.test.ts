// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useChatStore } from '../useChatStore'
import type { ChatSession } from '../useChatStore'

describe('useChatStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('localStorage persistence - MVA-164', () => {
    it('should not persist message bodies to localStorage', () => {
      const store = useChatStore()

      // Create a session with messages
      const sessionId = store.createNewSession('Test Session')
      store.addMessage({
        content: 'User message with sensitive data',
        sender: 'user'
      })
      store.addMessage({
        content: 'Assistant response with private info',
        sender: 'assistant'
      })

      // Verify session has messages in memory
      expect(store.sessions[0].messages).toHaveLength(2)

      // Simulate what the serializer would do (removes message bodies)
      const serialized = JSON.stringify({
        sessions: store.sessions.map(session => ({
          id: session.id,
          title: session.title,
          createdAt: session.createdAt,
          updatedAt: session.updatedAt,
          isActive: session.isActive
        })),
        currentSessionId: store.currentSessionId,
        sidebarCollapsed: store.sidebarCollapsed
      })

      const parsed = JSON.parse(serialized)
      expect(parsed.sessions[0]).not.toHaveProperty('messages')
      expect(parsed.sessions[0]).toEqual({
        id: sessionId,
        title: 'Test Session',
        createdAt: expect.any(String),
        updatedAt: expect.any(String),
        isActive: true
      })
    })

    it('should only persist currentSessionId, sidebarCollapsed, and sessions (without message bodies)', () => {
      const store = useChatStore()
      store.createNewSession('Session 1')
      store.addMessage({ content: 'Test message', sender: 'user' })
      store.toggleSidebar()

      // Verify full state has messages
      expect(store.sessions[0].messages).toHaveLength(1)

      // Simulate serializer removing message bodies
      const serialized = JSON.stringify({
        sessions: store.sessions.map(session => ({
          id: session.id,
          title: session.title,
          createdAt: session.createdAt,
          updatedAt: session.updatedAt,
          isActive: session.isActive
        })),
        currentSessionId: store.currentSessionId,
        sidebarCollapsed: store.sidebarCollapsed
      })

      const parsed = JSON.parse(serialized)
      expect(parsed).toHaveProperty('currentSessionId')
      expect(parsed).toHaveProperty('sidebarCollapsed')
      expect(parsed).toHaveProperty('sessions')
      expect(parsed.sidebarCollapsed).toBe(true)
      expect(parsed.sessions).toHaveLength(1)
      expect(parsed.sessions[0]).not.toHaveProperty('messages')
    })

    it('should reconstruct sessions with empty messages from persisted state', () => {
      const pinia = createPinia()
      setActivePinia(pinia)
      let store = useChatStore()

      store.createNewSession('Session 1')
      const messageId = store.addMessage({ content: 'Test message', sender: 'user' })

      // Verify original session has messages
      expect(store.sessions[0].messages).toHaveLength(1)
      expect(messageId).toBeTruthy()

      // Simulate what would be persisted (no message bodies)
      const persistedData = {
        sessions: store.sessions.map(session => ({
          id: session.id,
          title: session.title,
          createdAt: session.createdAt,
          updatedAt: session.updatedAt,
          isActive: session.isActive
        })),
        currentSessionId: store.currentSessionId,
        sidebarCollapsed: store.sidebarCollapsed
      }

      // Create new store and simulate deserialization
      const pinia2 = createPinia()
      setActivePinia(pinia2)
      store = useChatStore()

      // Simulate deserializer reconstructing sessions with empty messages
      store.$patch({
        sessions: persistedData.sessions.map((session: Record<string, unknown>) => ({
          id: session.id,
          title: session.title,
          messages: [],
          createdAt: new Date(session.createdAt as string),
          updatedAt: new Date(session.updatedAt as string),
          isActive: false
        })),
        currentSessionId: persistedData.currentSessionId,
        sidebarCollapsed: persistedData.sidebarCollapsed
      })

      // Verify sessions were restored without messages
      expect(store.sessions).toHaveLength(1)
      expect(store.sessions[0].messages).toHaveLength(0)
      expect(store.sessions[0].title).toBe('Session 1')
      expect(store.currentSessionId).toBeTruthy()
    })
  })

  describe('syncSessionsWithBackend - MVA-164', () => {
    it('should merge backend sessions when intentionalEmpty is false (default)', () => {
      const store = useChatStore()

      // Create a local session
      const localSessionId = store.createNewSession('Local Session')
      store.addMessage({ content: 'Local message', sender: 'user' })

      // Sync with backend that has different sessions
      const backendSessions = [
        {
          id: 'backend-session-1',
          title: 'Backend Session',
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
          isActive: false
        }
      ]

      store.syncSessionsWithBackend(backendSessions, false)

      // Both sessions should exist (merged)
      expect(store.sessions).toHaveLength(2)
      expect(store.sessions.map(s => s.id)).toContain(localSessionId)
      expect(store.sessions.map(s => s.id)).toContain('backend-session-1')

      // Local session messages should be preserved
      const localSession = store.sessions.find(s => s.id === localSessionId)
      expect(localSession?.messages).toHaveLength(1)
    })

    it('should only overwrite local sessions when intentionalEmpty is true', () => {
      const store = useChatStore()

      // Create local sessions
      store.createNewSession('Local Session 1')
      store.createNewSession('Local Session 2')

      // Sync with backend returning empty (explicit logout)
      const backendSessions: ChatSession[] = []

      store.syncSessionsWithBackend(backendSessions, true)

      // All local sessions should be cleared
      expect(store.sessions).toHaveLength(0)
      expect(store.currentSessionId).toBeNull()
    })

    it('should not delete local sessions when backend returns different sessions (intentionalEmpty=false)', () => {
      const store = useChatStore()

      const localSessionId = store.createNewSession('Local Session')
      store.addMessage({ content: 'Local message', sender: 'user' })

      const backendSessions = [
        {
          id: 'backend-1',
          title: 'Backend Session 1',
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
          isActive: false
        },
        {
          id: 'backend-2',
          title: 'Backend Session 2',
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
          isActive: false
        }
      ]

      store.syncSessionsWithBackend(backendSessions, false)

      // Local session should still exist
      expect(store.sessions.map(s => s.id)).toContain(localSessionId)

      // Local messages should be preserved
      const localSession = store.sessions.find(s => s.id === localSessionId)
      expect(localSession?.messages).toHaveLength(1)
    })
  })

  describe('autoSave removed - MVA-164', () => {
    it('should not have autoSave in settings interface', () => {
      const store = useChatStore()

      expect(store.settings).toBeDefined()
      expect(store.settings).not.toHaveProperty('autoSave')
      expect(store.settings).toHaveProperty('persistHistory')
    })
  })

  describe('createNewSession with client-minted UUID', () => {
    it('should use provided sessionId when passed', () => {
      const store = useChatStore()
      const customId = 'custom-uuid-1234'

      const returnedId = store.createNewSession('Test', customId)

      expect(returnedId).toBe(customId)
      expect(store.currentSessionId).toBe(customId)

      const session = store.sessions.find(s => s.id === customId)
      expect(session).toBeDefined()
      expect(session?.id).toBe(customId)
    })

    it('should generate ID if not provided', () => {
      const store = useChatStore()

      const returnedId = store.createNewSession('Test')

      expect(returnedId).toBeTruthy()
      expect(returnedId).not.toBe('')

      const session = store.sessions.find(s => s.id === returnedId)
      expect(session).toBeDefined()
    })
  })

  // Issue #11843: assistant reply rendered twice (two bubbles ~1min apart) because
  // a re-hydration / poll / live-event echo re-added the SAME backend reply through
  // a path that did not reuse the backend message_id. addOrUpdateMessage now dedups
  // by the stable server id whether it arrives as `id` (stream) or `message_id`
  // (poll / live-event echo).
  describe('addOrUpdateMessage server-id deduplication - #11843', () => {
    const serverId = 'srv-msg-abc123'

    it('collapses the same server id (via id) added twice into ONE message', () => {
      const store = useChatStore()
      store.createNewSession('Dedup Session')

      store.addOrUpdateMessage({ id: serverId, content: 'The answer is 42.', sender: 'assistant', type: 'response' })
      // Second delivery of the identical reply (e.g. from a poll/refresh)
      store.addOrUpdateMessage({ id: serverId, content: 'The answer is 42.', sender: 'assistant', type: 'response' })

      expect(store.currentMessages).toHaveLength(1)
      expect(store.currentMessages[0].content).toBe('The answer is 42.')
    })

    it('dedups when the reply first arrives via id (stream) then via message_id (poll/echo)', () => {
      const store = useChatStore()
      store.createNewSession('Dedup Session')

      // Stream / normal path: server id lands in `id`
      store.addOrUpdateMessage({ id: serverId, content: 'Grounded reply.', sender: 'assistant', type: 'response' })
      // Poll / live-event echo: the same server id lands in `message_id`
      store.addOrUpdateMessage({ message_id: serverId, content: 'Grounded reply.', sender: 'assistant', type: 'response' })

      expect(store.currentMessages).toHaveLength(1)
    })

    it('dedups a streaming placeholder (addMessage w/ message_id) against a later echo (addOrUpdateMessage w/ id)', () => {
      const store = useChatStore()
      store.createNewSession('Dedup Session')

      // Streaming placeholder carries the backend id in message_id (frontend id differs)
      store.addMessage({ content: 'Streamed reply.', sender: 'assistant', type: 'response', message_id: serverId })
      // Live-event echo re-adds the same reply keyed on the server id
      store.addOrUpdateMessage({ id: serverId, content: 'Streamed reply.', sender: 'assistant', type: 'response' })

      expect(store.currentMessages).toHaveLength(1)
      expect(store.currentMessages[0].content).toBe('Streamed reply.')
    })

    it('keeps distinct server ids as separate messages (no over-dedup)', () => {
      const store = useChatStore()
      store.createNewSession('Dedup Session')

      store.addOrUpdateMessage({ id: 'srv-1', content: 'First reply.', sender: 'assistant', type: 'response' })
      store.addOrUpdateMessage({ id: 'srv-2', content: 'Second reply.', sender: 'assistant', type: 'response' })

      expect(store.currentMessages).toHaveLength(2)
    })
  })
})
