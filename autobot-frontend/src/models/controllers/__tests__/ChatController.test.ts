// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ChatController } from '../ChatController'
import * as chatRepository from '@/models/repositories'

// Mock the repositories
vi.mock('@/models/repositories', () => ({
  chatRepository: {
    createNewChat: vi.fn(),
    sendMessage: vi.fn(),
    getChatList: vi.fn(),
    getChatMessages: vi.fn(),
    saveChatMessages: vi.fn(),
    deleteChat: vi.fn(),
    resetChat: vi.fn(),
    getSessionFacts: vi.fn(),
    preserveSessionFacts: vi.fn()
  }
}))

// Mock the store
vi.mock('@/stores/useChatStore', () => ({
  useChatStore: vi.fn(() => ({
    createNewSession: vi.fn((title: string, sessionId: string) => sessionId),
    switchToSession: vi.fn(),
    addMessage: vi.fn(),
    updateMessage: vi.fn(),
    deleteMessage: vi.fn(),
    deleteSession: vi.fn(),
    clearAllSessions: vi.fn(),
    sessions: [],
    currentSessionId: null,
    currentSession: null,
    setTyping: vi.fn(),
    setStreamingPreview: vi.fn(),
    setPendingApproval: vi.fn(),
    updateSettings: vi.fn(),
    toggleSidebar: vi.fn(),
    isTyping: false,
    settings: { autoSave: false, persistHistory: true }
  }))
}))

// Mock the appStore
vi.mock('@/stores/useAppStore', () => ({
  useAppStore: vi.fn(() => ({
    setGlobalError: vi.fn()
  }))
}))

describe('ChatController', () => {
  let controller: ChatController

  beforeEach(() => {
    vi.clearAllMocks()
    controller = new ChatController()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('createNewSession', () => {
    it('should call backend with client-minted UUID before setting currentSessionId', async () => {
      const mockBackendResponse = { id: 'uuid-1234', title: 'Test Chat' }
      vi.mocked(chatRepository.chatRepository.createNewChat).mockResolvedValue(mockBackendResponse)

      const sessionId = await controller.createNewSession('Test Chat')

      // Verify backend was called with a UUID
      expect(chatRepository.chatRepository.createNewChat).toHaveBeenCalledWith(
        'Test Chat',
        undefined,
        expect.stringMatching(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i)
      )

      // Verify the returned sessionId matches the backend call
      expect(sessionId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i)
    })

    it('should throw if backend create fails', async () => {
      const error = new Error('Backend error')
      vi.mocked(chatRepository.chatRepository.createNewChat).mockRejectedValue(error)

      await expect(controller.createNewSession('Test Chat')).rejects.toThrow('Backend error')

      // Verify backend was called
      expect(chatRepository.chatRepository.createNewChat).toHaveBeenCalled()
    })

    it('should call store.createNewSession with the client-minted UUID', async () => {
      const mockBackendResponse = { id: 'uuid-1234', title: 'Test Chat' }
      vi.mocked(chatRepository.chatRepository.createNewChat).mockResolvedValue(mockBackendResponse)

      const sessionId = await controller.createNewSession('Test Chat')

      // Get the store to verify the call
      const store = controller['chatStore']
      expect(store.createNewSession).toHaveBeenCalledWith('Test Chat', sessionId)
    })
  })

  describe('autoSave methods removed', () => {
    it('should not have enableAutoSave method', () => {
      expect((controller as unknown as Record<string, unknown>).enableAutoSave).toBeUndefined()
    })

    it('should not have disableAutoSave method', () => {
      expect((controller as unknown as Record<string, unknown>).disableAutoSave).toBeUndefined()
    })

    it('should not have _autoSaveIntervalId field', () => {
      expect((controller as unknown as Record<string, unknown>)._autoSaveIntervalId).toBeUndefined()
    })
  })
})
