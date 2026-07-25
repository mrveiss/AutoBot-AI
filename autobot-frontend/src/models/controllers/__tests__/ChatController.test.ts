// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ChatController } from '../ChatController'
import * as chatRepository from '@/models/repositories'
import { useChatStore } from '@/stores/useChatStore'
import { useAppStore } from '@/stores/useAppStore'
import i18n from '@/i18n'

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
    activeChatContext: {},          // #11690: no scope in the general path
    setActiveChatContext: vi.fn(),  // #11690
    settings: { autoSave: false, persistHistory: true }
  }))
}))

// Mock the appStore
vi.mock('@/stores/useAppStore', () => ({
  useAppStore: vi.fn(() => ({
    setGlobalError: vi.fn()
  }))
}))

// Mock the request queue so send flows run the enqueued fn synchronously
vi.mock('@/composables/useRequestQueue', () => ({
  requestQueue: {
    enqueue: vi.fn(({ fn }: { fn: () => unknown }) => fn())
  }
}))

// Mock ApiClient (cache invalidation is a no-op side effect on send)
vi.mock('@/utils/ApiClient', () => ({
  default: {
    invalidateCache: vi.fn()
  }
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

  describe('sendMessage activeChatContext merge (#11690)', () => {
    // Build a store whose activeChatContext scopes sends to a company, with an
    // existing session so the send path never has to mint a new one.
    function scopedStore(context: Record<string, unknown>) {
      return {
        createNewSession: vi.fn((title: string, sessionId: string) => sessionId),
        switchToSession: vi.fn(),
        addMessage: vi.fn(() => 'user-msg-1'),
        updateMessage: vi.fn(),
        setTyping: vi.fn(),
        sessions: [],
        currentSessionId: 'session-1',
        activeChatContext: context,
        settings: { autoSave: false, persistHistory: true }
      }
    }

    it('merges activeChatContext into the send options', async () => {
      vi.mocked(useChatStore).mockReturnValue(
        scopedStore({ company_id: 'company-42' }) as unknown as ReturnType<typeof useChatStore>
      )
      vi.mocked(chatRepository.chatRepository.sendMessage).mockResolvedValue({
        type: 'json',
        data: {}
      } as never)

      await controller.sendMessage('hello CEO')

      expect(chatRepository.chatRepository.sendMessage).toHaveBeenCalledWith(
        'hello CEO',
        'session-1',
        expect.objectContaining({ company_id: 'company-42' })
      )
    })

    it('lets explicit call-site options win over activeChatContext', async () => {
      vi.mocked(useChatStore).mockReturnValue(
        scopedStore({ company_id: 'company-42' }) as unknown as ReturnType<typeof useChatStore>
      )
      vi.mocked(chatRepository.chatRepository.sendMessage).mockResolvedValue({
        type: 'json',
        data: {}
      } as never)

      await controller.sendMessage('hello CEO', { company_id: 'override-7', extra: true })

      expect(chatRepository.chatRepository.sendMessage).toHaveBeenCalledWith(
        'hello CEO',
        'session-1',
        expect.objectContaining({ company_id: 'override-7', extra: true })
      )
    })

    it('leaves send options untouched when no context is active', async () => {
      vi.mocked(useChatStore).mockReturnValue(
        scopedStore({}) as unknown as ReturnType<typeof useChatStore>
      )
      vi.mocked(chatRepository.chatRepository.sendMessage).mockResolvedValue({
        type: 'json',
        data: {}
      } as never)

      await controller.sendMessage('hi there')

      const [, , sentOptions] = vi.mocked(chatRepository.chatRepository.sendMessage).mock.calls[0]
      expect(sentOptions).not.toHaveProperty('company_id')
    })
  })

  describe('deleteChatSession backend-failure handling (#12327)', () => {
    // Build a store exposing a deleteSession spy and a sessions list so the
    // controller's local-removal step can be observed.
    function deletableStore() {
      return {
        deleteSession: vi.fn(),
        sessions: [{ id: 's1' }],
        currentSessionId: 's1'
      }
    }

    it('keeps the chat locally and surfaces an error when the backend delete fails', async () => {
      const store = deletableStore()
      vi.mocked(useChatStore).mockReturnValue(
        store as unknown as ReturnType<typeof useChatStore>
      )
      const setGlobalError = vi.fn()
      vi.mocked(useAppStore).mockReturnValue(
        { setGlobalError } as unknown as ReturnType<typeof useAppStore>
      )
      // A network failure has no HTTP status — the mirror of the reported case.
      vi.mocked(chatRepository.chatRepository.deleteChat).mockRejectedValue(
        new Error('Network Error')
      )

      await expect(controller.deleteChatSession('s1')).rejects.toThrow('Network Error')

      // The chat must NOT be removed locally, and the user must be told it failed.
      expect(store.deleteSession).not.toHaveBeenCalled()
      expect(setGlobalError).toHaveBeenCalledTimes(1)
    })

    it('removes the chat locally when the backend delete succeeds', async () => {
      const store = deletableStore()
      vi.mocked(useChatStore).mockReturnValue(
        store as unknown as ReturnType<typeof useChatStore>
      )
      vi.mocked(chatRepository.chatRepository.deleteChat).mockResolvedValue(
        undefined as never
      )

      await controller.deleteChatSession('s1')

      expect(chatRepository.chatRepository.deleteChat).toHaveBeenCalledWith(
        's1',
        undefined,
        undefined
      )
      expect(store.deleteSession).toHaveBeenCalledWith('s1')
    })

    it('reconciles local state when the backend returns 404 (already gone)', async () => {
      const store = deletableStore()
      vi.mocked(useChatStore).mockReturnValue(
        store as unknown as ReturnType<typeof useChatStore>
      )
      vi.mocked(chatRepository.chatRepository.deleteChat).mockRejectedValue(
        Object.assign(new Error('Not Found'), { status: 404 })
      )

      await controller.deleteChatSession('s1')

      expect(store.deleteSession).toHaveBeenCalledWith('s1')
    })
  })

  describe('sendMessage error categorization (#12401)', () => {
    // A store with an existing session so the send path goes straight to the
    // repository call (and its error handling) without minting a new session.
    function sendReadyStore() {
      return {
        createNewSession: vi.fn((title: string, sessionId: string) => sessionId),
        switchToSession: vi.fn(),
        addMessage: vi.fn(() => 'user-msg-1'),
        updateMessage: vi.fn(),
        setTyping: vi.fn(),
        sessions: [],
        currentSession: null,
        currentSessionId: 'session-1',
        activeChatContext: {},
        settings: { autoSave: false, persistHistory: true }
      }
    }

    it('surfaces invalidFormat (not the generic sendFailed) for a 422 error', async () => {
      vi.mocked(useChatStore).mockReturnValue(
        sendReadyStore() as unknown as ReturnType<typeof useChatStore>
      )
      const setGlobalError = vi.fn()
      vi.mocked(useAppStore).mockReturnValue(
        { setGlobalError } as unknown as ReturnType<typeof useAppStore>
      )
      // A 422 carries an HTTP status; #12401 must preserve it through the
      // re-wrap so getUserFriendlyErrorMessage() can categorize it.
      vi.mocked(chatRepository.chatRepository.sendMessage).mockRejectedValue(
        Object.assign(new Error('field required'), { status: 422 })
      )
      // Collapse the inter-retry backoff so the test is fast.
      ;(controller as unknown as { retryDelay: number }).retryDelay = 0

      await expect(controller.sendMessage('hello')).rejects.toBeTruthy()

      // The categorized message surfaces exactly once — not the double-wrapped
      // sendFailed that resulted before status was preserved.
      expect(setGlobalError).toHaveBeenCalledTimes(1)
      expect(setGlobalError).toHaveBeenCalledWith(
        i18n.global.t('chat.errors.invalidFormat')
      )
    })

    it('surfaces networkFailed (not the generic sendFailed) for a NetworkError', async () => {
      vi.mocked(useChatStore).mockReturnValue(
        sendReadyStore() as unknown as ReturnType<typeof useChatStore>
      )
      const setGlobalError = vi.fn()
      vi.mocked(useAppStore).mockReturnValue(
        { setGlobalError } as unknown as ReturnType<typeof useAppStore>
      )
      // A network failure carries name==='NetworkError'; #12401 must preserve it.
      vi.mocked(chatRepository.chatRepository.sendMessage).mockRejectedValue(
        Object.assign(new Error('connection refused'), { name: 'NetworkError' })
      )
      ;(controller as unknown as { retryDelay: number }).retryDelay = 0

      await expect(controller.sendMessage('hello')).rejects.toBeTruthy()

      expect(setGlobalError).toHaveBeenCalledTimes(1)
      expect(setGlobalError).toHaveBeenCalledWith(
        i18n.global.t('chat.errors.networkFailed')
      )
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
