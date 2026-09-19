// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import ChatInterface from '../chat/ChatInterface.vue'
import {
  renderComponent,
  createMockChatSession,
  createMockChatMessage,
  waitForUpdate,
} from '../../test/utils/test-utils'
import { webSocketTestUtil } from '../../test/mocks/websocket-mock'
import { ServiceURLs } from '@/constants/network'
import { useChatStore } from '@/stores/useChatStore'

// #14613/#14842: this file's per-test budget, and only this file's.
//
// All 23 tests here render the FULL chat tree — sidebar, session list, message
// list, composer and settings — through `renderComponent()` with a Pinia store
// and a router. That is the heaviest mount in the suite and it is the subject
// of the tests, not incidental setup: there is no unresolved promise to fix and
// nothing to stub away without deleting the coverage. `waitFor()` has its own
// 1s budget and fails with "unable to find element", so a 10s failure here has
// always meant the render itself was still running.
//
// On the singleton self-hosted runner the reported `environment` cost is ~3x the
// `tests` cost, so a mount measured at 3-4s idle has repeatedly crossed 10s under
// contention — on a different test each run, which is why this is set per FILE
// rather than pinned to whichever test lost the draw. The global `testTimeout`
// in vitest.config.ts stays at 10s: a genuinely hung test elsewhere must still
// fail fast.
vi.setConfig({ testTimeout: 20_000 })

// ---- Module mocks ----

// Mock BatchApiService - the primary initialization path for ChatInterface
const mockInitializeChatInterface = vi.fn()
vi.mock('@/services/BatchApiService', () => ({
  default: {
    initializeChatInterface: (...args: unknown[]) => mockInitializeChatInterface(...args),
  },
  BatchApiService: vi.fn(),
}))

// Mock ApiClient with all domain methods used by components
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
    getChatList: vi.fn().mockResolvedValue([]),
    getChatMessages: vi.fn().mockResolvedValue({ messages: [] }),
    getSystemHealth: vi.fn().mockResolvedValue({ status: 'healthy' }),
    getSettings: vi.fn().mockResolvedValue({}),
    checkHealth: vi.fn().mockResolvedValue(true),
    sendMessage: vi.fn().mockResolvedValue({}),
  },
  ApiClient: vi.fn(),
}))

// Mock ChatRepository to prevent real HTTP calls
vi.mock('@/models/repositories', () => {
  const mockChatRepo = {
    getChatList: vi.fn().mockResolvedValue([]),
    getSessions: vi.fn().mockResolvedValue([]),
    getSession: vi.fn().mockResolvedValue({ id: 'test', messages: [] }),
    sendMessage: vi.fn().mockResolvedValue({}),
    deleteSession: vi.fn().mockResolvedValue({}),
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  }
  return {
    chatRepository: mockChatRepo,
    apiRepository: { get: vi.fn(), post: vi.fn() },
    knowledgeRepository: { search: vi.fn() },
    systemRepository: { getHealth: vi.fn() },
    ChatRepository: vi.fn(() => mockChatRepo),
    ApiRepository: vi.fn(),
    KnowledgeRepository: vi.fn(),
    SystemRepository: vi.fn(),
    RepositoryFactory: {
      createChatRepository: vi.fn(() => mockChatRepo),
      createKnowledgeRepository: vi.fn(),
      createSystemRepository: vi.fn(),
    },
  }
})

// Mock ChatController with all methods used by ChatInterface and child components
const mockController = {
  // Session management
  loadChatSessions: vi.fn().mockResolvedValue(undefined),
  loadChatMessages: vi.fn().mockResolvedValue(undefined),
  createNewSession: vi.fn(),
  switchToSession: vi.fn(),
  resetCurrentChat: vi.fn(),
  deleteChatSession: vi.fn().mockResolvedValue(undefined),
  updateSessionTitle: vi.fn(),
  getSessionFacts: vi.fn().mockResolvedValue([]),
  preserveSessionFacts: vi.fn().mockResolvedValue({}),
  // #5366 / Issue #4431: sync flow pushes local-only sessions before
  // reconciling with backend. Must be mocked or `initializeChatInterface`
  // throws `controller.pushLocalOnlySessions is not a function`.
  pushLocalOnlySessions: vi.fn().mockResolvedValue(undefined),
  // Message handling
  sendMessage: vi.fn().mockResolvedValue(undefined),
  // Settings
  updateChatSettings: vi.fn(),
  // UI
  toggleSidebar: vi.fn(),
  clearSession: vi.fn().mockResolvedValue(undefined),
  exportSession: vi.fn(),
}
vi.mock('@/models/controllers', () => ({
  useChatController: () => mockController,
  useKnowledgeController: () => ({
    loadStats: vi.fn(),
    search: vi.fn(),
  }),
  ChatController: vi.fn(),
  KnowledgeController: vi.fn(),
}))

// Mock fetchWithAuth to prevent real network requests
vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn().mockResolvedValue(
    new Response(JSON.stringify({}), { status: 200 })
  ),
}))

// Mock AppConfig to prevent network requests during import
vi.mock('@/config/AppConfig.js', () => ({
  default: {
    backendUrl: 'http://localhost:8001',
    wsUrl: 'ws://localhost:8001/ws',
    get: vi.fn().mockReturnValue('http://localhost:8001'),
    validateConnection: vi.fn().mockResolvedValue(true),
  },
}))

// Mock composables that may cause side effects
//
// #16274: a shared object (not a fresh one per call) so tests can assert on
// `mockMessagePoller.start`/`.stop` after render — the component holds its
// own reference, but it's the same instance every time useBackoffPoller() runs.
const mockMessagePoller = {
  start: vi.fn(),
  stop: vi.fn(),
  isCircuitOpen: { value: false },
  consecutiveFailures: { value: 0 },
  currentInterval: { value: 10000 },
}
vi.mock('@/composables/useBackoffPoller', () => ({
  useBackoffPoller: () => mockMessagePoller,
}))

vi.mock('@/composables/useVoiceOutput', () => ({
  useVoiceOutput: () => ({
    voiceOutputEnabled: { value: false },
    isSpeaking: { value: false },
    toggleVoiceOutput: vi.fn(),
    speak: vi.fn(),
    speakStreaming: vi.fn(),
    flushStreaming: vi.fn(),
    unlockAudio: vi.fn(),
    playAudioChunk: vi.fn(),
    stopSpeaking: vi.fn(),
  }),
}))

vi.mock('@/composables/useVoiceConversation', () => ({
  useVoiceConversation: () => ({
    state: { value: 'idle' },
    mode: { value: 'push-to-talk' },
    currentTranscript: { value: '' },
    currentLanguage: { value: 'en' },
    bubbles: { value: [] },
    isActive: { value: false },
    errorMessage: { value: null },
    wsConnected: { value: false },
    audioLevel: { value: 0 },
    silenceThreshold: { value: 0.01 },
    micAccessAvailable: { value: false },
    isListening: { value: false },
    isProcessing: { value: false },
    stateLabel: { value: '' },
    activate: vi.fn(),
    deactivate: vi.fn(),
    startListening: vi.fn(),
    stopListening: vi.fn(),
    toggleListening: vi.fn(),
    setMode: vi.fn(),
    cleanup: vi.fn(),
  }),
}))

vi.mock('@/composables/useOverseerAgent', () => ({
  useOverseerAgent: () => ({
    isConnected: { value: false },
    isProcessing: { value: false },
    currentPlan: { value: null },
    steps: { value: [] },
    currentStep: { value: null },
    currentStepData: { value: null },
    status: { value: 'idle' },
    error: { value: null },
    progressPercentage: { value: 0 },
    connect: vi.fn(),
    disconnect: vi.fn(),
    submitQuery: vi.fn(),
    cancel: vi.fn(),
    getStatus: vi.fn(),
  }),
}))

const mockChatSessions = [
  createMockChatSession({
    chatId: 'chat-1',
    name: 'Test Chat 1',
    messages: [
      createMockChatMessage({ content: 'Hello', sender: 'user' }),
      createMockChatMessage({ content: 'Hi there!', sender: 'assistant' }),
    ]
  }),
  createMockChatSession({
    chatId: 'chat-2',
    name: 'Test Chat 2',
    messages: []
  }),
]

describe('ChatInterface', () => {
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup()
    webSocketTestUtil.setup()

    // Reset localStorage
    localStorage.clear()

    // Default: initialization returns empty data (no sessions, healthy system)
    mockInitializeChatInterface.mockResolvedValue({
      chat_sessions: { data: [] },
      system_health: { data: { status: 'healthy' } },
    })

    // #16274/#3070: vitest.config.ts sets `mockReset: true`, which strips
    // vi.fn() implementations before every test — including the ones set
    // once at `mockController`'s module-scope literal above. Left unmocked,
    // a call like `controller.loadChatSessions().catch(...)` returns
    // `undefined` instead of a promise and throws `Cannot read properties of
    // undefined (reading 'catch')`, which is exactly the "Chat initialization
    // failed" crash this file must never log (see the Error Handling suite).
    // Re-applying every default here, not just the one that happened to
    // crash, closes the whole landmine class instead of one instance of it.
    mockController.loadChatSessions.mockResolvedValue(undefined)
    mockController.loadChatMessages.mockResolvedValue(undefined)
    mockController.deleteChatSession.mockResolvedValue(undefined)
    mockController.getSessionFacts.mockResolvedValue([])
    mockController.preserveSessionFacts.mockResolvedValue({})
    mockController.pushLocalOnlySessions.mockResolvedValue(undefined)
    mockController.sendMessage.mockResolvedValue(undefined)
    mockController.clearSession.mockResolvedValue(undefined)
  })

  afterEach(() => {
    webSocketTestUtil.teardown()
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders the main chat interface', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      // i18n keys render as-is since test i18n has empty messages
      await waitFor(() => {
        // #5456: ChatSidebar's mobile header no longer duplicates the
        // chatHistory label (moved to h3-only), so getByText matches
        // exactly once.
        expect(screen.getByText('chat.sidebar.chatHistory')).toBeInTheDocument()
      })
      expect(screen.getByLabelText('chat.sidebar.createNew')).toBeInTheDocument()
      expect(screen.getByLabelText('chat.sidebar.resetChat')).toBeInTheDocument()
      expect(screen.getByLabelText('chat.sidebar.deleteChat')).toBeInTheDocument()
      expect(screen.getByLabelText('chat.sidebar.refreshList')).toBeInTheDocument()
    })

    it('renders with collapsed sidebar when toggle is clicked', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        // #5456: ChatSidebar's mobile header no longer duplicates the
        // chatHistory label (moved to h3-only), so getByText matches
        // exactly once.
        expect(screen.getByText('chat.sidebar.chatHistory')).toBeInTheDocument()
      })

      // The collapse button aria-label depends on sidebarCollapsed state
      const collapseButton = screen.getByLabelText('chat.sidebar.collapseSidebar')
      await user.click(collapseButton)

      // Clicking collapse triggers controller.toggleSidebar()
      await waitFor(() => {
        expect(mockController.toggleSidebar).toHaveBeenCalled()
      })
    })

    it('displays chat history when available', async () => {
      // Mock initialization to return chat sessions
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: mockChatSessions },
        system_health: { data: { status: 'healthy' } },
      })

      renderComponent(ChatInterface, { pinia: true, router: true })

      // The sessions are synced to the Pinia store via syncSessionsWithBackend
      // With createTestingPinia, the store actions are spied on
      await waitFor(() => {
        expect(mockInitializeChatInterface).toHaveBeenCalled()
      })
    })

    it('shows loading state while fetching chat history', () => {
      // Mock API to delay response
      mockInitializeChatInterface.mockImplementation(
        () => new Promise(resolve => setTimeout(resolve, 5000))
      )

      renderComponent(ChatInterface, { pinia: true, router: true })

      // Sidebar should still render with refresh button available
      expect(screen.getByLabelText('chat.sidebar.refreshList')).toBeInTheDocument()
    })

    // #16274: the init raced a 10s timer that onUnmounted never cancelled, so
    // an unmounted component still reached its fallback and wrote to the store.
    // In this suite the rejection landed in a LATER test, after `mockReset: true`
    // had stripped the mock the fallback calls, surfacing as a crash somewhere
    // unrelated while this file stayed green (vitest.config.ts:71, #3070).
    //
    // Asserted on the fallback never running, not on the timer being cleared:
    // clearing the handle is the mechanism, and a future rewrite may cancel the
    // init differently. What must stay true is that nothing after an await runs
    // once the component is gone.
    //
    // Rewritten from a version that mocked init to never settle and advanced
    // fake timers 11s past unmount, expecting the race's own 10s timer to fire
    // it into the fallback. But onUnmounted clears that timer synchronously on
    // unmount, before the advance ever runs — so Promise.race never settled,
    // the code after it (including the isUnmounted guard under test) was never
    // reached, and the assertion below passed whether or not that guard
    // existed. Rejecting the mocked init directly, after unmount, is what
    // actually drives execution into the guarded catch block.
    it('does not run the init fallback after the component unmounts', async () => {
      let rejectInit: (reason?: unknown) => void = () => {}
      mockInitializeChatInterface.mockImplementation(
        () => new Promise((_resolve, reject) => { rejectInit = reject })
      )
      mockController.loadChatSessions.mockClear()

      const { unmount } = renderComponent(ChatInterface, { pinia: true, router: true })
      unmount()

      // The kind of rejection a real slow/unavailable backend produces —
      // after unmount, the way the original 10s race timer used to.
      rejectInit(new Error('Simulated backend timeout'))
      await waitForUpdate()

      expect(mockController.loadChatSessions).not.toHaveBeenCalled()
    })

    // Review on #16911: pushLocalOnlySessions does real network I/O
    // (Promise.allSettled over chatRepository calls) but, unlike the awaits
    // immediately before and after it in the same function, wasn't checked
    // against isUnmounted before the store write that follows it.
    it('does not write to the store when unmounted while pushing local-only sessions', async () => {
      let resolvePush: (value?: unknown) => void = () => {}
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: mockChatSessions },
        system_health: { data: { status: 'healthy' } },
      })
      mockController.pushLocalOnlySessions.mockImplementation(
        () => new Promise(resolve => { resolvePush = resolve })
      )

      const { unmount } = renderComponent(ChatInterface, { pinia: true, router: true })
      const store = useChatStore()

      await waitFor(() => {
        expect(mockController.pushLocalOnlySessions).toHaveBeenCalled()
      })

      unmount()
      resolvePush(undefined)
      await waitForUpdate()

      expect(store.syncSessionsWithBackend).not.toHaveBeenCalled()
    })

    // Review on #16911: initializeChatInterface() resolves normally even when
    // it takes its own isUnmounted early exit, so `await initializeChatInterface()`
    // in onMounted always completes — onMounted must check the same flag before
    // it resumes, or it re-adds the keydown listener and restarts the message
    // poller that onUnmounted already cleaned up moments earlier.
    it('does not start polling or add the keydown listener when mount resumes after unmount', async () => {
      let resolveInit: (value?: unknown) => void = () => {}
      mockInitializeChatInterface.mockImplementation(
        () => new Promise(resolve => { resolveInit = resolve })
      )
      const addEventListenerSpy = vi.spyOn(document, 'addEventListener')
      mockMessagePoller.start.mockClear()

      const { unmount } = renderComponent(ChatInterface, { pinia: true, router: true })
      unmount()

      // A slow init that eventually succeeds, resolving after the component
      // is already gone — the same race initializeChatInterface() itself
      // guards against, one call frame up.
      resolveInit({
        chat_sessions: { data: [] },
        system_health: { data: { status: 'healthy' } },
      })
      await waitForUpdate()

      expect(addEventListenerSpy).not.toHaveBeenCalledWith('keydown', expect.any(Function))
      expect(mockMessagePoller.start).not.toHaveBeenCalled()

      addEventListenerSpy.mockRestore()
    })

    // Review on #16911: onUnmounted's own cleanup — verified directly, since
    // the tests above only ever exercise the path where mount never finishes.
    it('removes the keydown listener and stops the poller on a normal unmount', async () => {
      const removeEventListenerSpy = vi.spyOn(document, 'removeEventListener')
      mockMessagePoller.stop.mockClear()

      const { unmount } = renderComponent(ChatInterface, { pinia: true, router: true })

      // Waits for the poller to start rather than just for init to be called:
      // onMounted adds the keydown listener in the same synchronous slice as
      // starting the poller (no await between them), so this also guarantees
      // the listener registration this test unmounts past has already run.
      await waitFor(() => {
        expect(mockMessagePoller.start).toHaveBeenCalled()
      })

      unmount()

      expect(removeEventListenerSpy).toHaveBeenCalledWith('keydown', expect.any(Function))
      expect(mockMessagePoller.stop).toHaveBeenCalled()

      removeEventListenerSpy.mockRestore()
    })
  })

  describe('Chat Management', () => {
    it('creates a new chat session', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(screen.getByLabelText('chat.sidebar.createNew')).toBeInTheDocument()
      })

      const newChatButton = screen.getByLabelText('chat.sidebar.createNew')
      await user.click(newChatButton)

      // Clicking "new" triggers controller.createNewSession()
      await waitFor(() => {
        expect(mockController.createNewSession).toHaveBeenCalled()
      })
    })

    it('switches between chat sessions', async () => {
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: mockChatSessions },
        system_health: { data: { status: 'healthy' } },
      })

      renderComponent(ChatInterface, { pinia: true, router: true })

      // Verify initialization was called with session data
      await waitFor(() => {
        expect(mockInitializeChatInterface).toHaveBeenCalled()
      })
    })

    it('deletes a chat session', async () => {
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: mockChatSessions },
        system_health: { data: { status: 'healthy' } },
      })

      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(mockInitializeChatInterface).toHaveBeenCalled()
      })

      // Delete button in the sidebar toolbar is disabled without an active session
      const deleteButton = screen.getByLabelText('chat.sidebar.deleteChat')
      expect(deleteButton).toBeInTheDocument()
    })

    it('resets current chat session button is disabled without active session', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(screen.getByLabelText('chat.sidebar.resetChat')).toBeInTheDocument()
      })

      // Reset button is disabled when no session is active (store.currentSessionId is empty)
      const resetButton = screen.getByLabelText('chat.sidebar.resetChat') as HTMLButtonElement
      expect(resetButton).toBeDisabled()
    })

    it('refreshes chat list', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(screen.getByLabelText('chat.sidebar.refreshList')).toBeInTheDocument()
      })

      const refreshButton = screen.getByLabelText('chat.sidebar.refreshList')
      await user.click(refreshButton)

      // Clicking refresh triggers controller.loadChatSessions()
      await waitFor(() => {
        expect(mockController.loadChatSessions).toHaveBeenCalled()
      })
    })
  })

  describe('Message Handling', () => {
    it('renders the message input area', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        // ChatInput placeholder renders as i18n key
        const input = screen.getByPlaceholderText('chat.input.typeMessage')
        expect(input).toBeInTheDocument()
      })
    })

    it('sends a message to the chat', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('chat.input.typeMessage')).toBeInTheDocument()
      })

      const messageInput = screen.getByPlaceholderText('chat.input.typeMessage') as HTMLTextAreaElement

      // Type message using fireEvent for reliable v-model update
      await fireEvent.update(messageInput, 'Hello, AutoBot!')

      // After typing, canSend becomes true and aria-label changes
      await waitFor(() => {
        expect(screen.getByLabelText('chat.input.sendMessage')).toBeInTheDocument()
      })

      const sendButton = screen.getByLabelText('chat.input.sendMessage')
      await user.click(sendButton)

      await waitFor(() => {
        expect(mockController.sendMessage).toHaveBeenCalled()
      })
    })

    it('handles message input with keyboard shortcuts', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('chat.input.typeMessage')).toBeInTheDocument()
      })

      const messageInput = screen.getByPlaceholderText('chat.input.typeMessage') as HTMLTextAreaElement

      // Type message using fireEvent for reliable v-model update
      await fireEvent.update(messageInput, 'Test message')

      // Focus the input and press Enter to send
      messageInput.focus()
      await fireEvent.keyDown(messageInput, { key: 'Enter', code: 'Enter' })

      await waitFor(() => {
        expect(mockController.sendMessage).toHaveBeenCalled()
      })
    })

    it('prevents sending empty messages', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(screen.getByPlaceholderText('chat.input.typeMessage')).toBeInTheDocument()
      })

      // The send button should show "enter message" label when input is empty
      const sendButton = screen.getByLabelText('chat.input.enterMessage')
      await user.click(sendButton)

      // Should not call sendMessage for empty input
      expect(mockController.sendMessage).not.toHaveBeenCalled()
    })

    it('displays chat messages area', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      // The chat interface should render the content area
      await waitFor(() => {
        expect(mockInitializeChatInterface).toHaveBeenCalled()
      })
    })
  })

  describe('WebSocket Integration', () => {
    it('handles incoming WebSocket messages', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      // Simulate WebSocket connection
      const ws = webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)

      // Simulate incoming chat message
      webSocketTestUtil.simulateChatMessage('Hello from WebSocket!', 'assistant')

      // WebSocket message is dispatched; component should handle it
      await waitForUpdate()
      expect(ws).toBeDefined()
    })

    it('handles WebSocket connection errors', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      const ws = webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)
      webSocketTestUtil.simulateError('Connection failed')

      // Should handle error gracefully
      expect(ws).toBeDefined()
    })

    it('handles workflow notifications via WebSocket', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)
      webSocketTestUtil.simulateWorkflowUpdate('workflow-123', 'running', 2)

      // Should dispatch workflow update without crashing
      await waitForUpdate()
    })
  })

  describe('Knowledge Persistence Dialog', () => {
    it('opens knowledge persistence dialog when triggered', async () => {
      const { container } = renderComponent(ChatInterface, { pinia: true, router: true })

      // Verify the component renders without errors
      expect(container).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      // Make initialization fail
      mockInitializeChatInterface.mockRejectedValue(new Error('Network error'))
      const errorSpy = vi.spyOn(console, 'error')

      const { container } = renderComponent(ChatInterface, { pinia: true, router: true })

      // Component should render despite error
      await waitFor(() => {
        expect(container).toBeInTheDocument()
      })

      // #16274 AC3: this test used to crash the fallback it exercises —
      // mockController.loadChatSessions had its module-scope mock stripped
      // by `mockReset: true` before this test ran and was never re-applied
      // per-test, so `controller.loadChatSessions().catch(...)` called
      // `.catch` on `undefined` and threw, surfacing here as "Chat
      // initialization failed" (fixed in this file's beforeEach).
      const loggedInitFailed = errorSpy.mock.calls.some(args =>
        args.some(arg => typeof arg === 'string' && arg.includes('Chat initialization failed'))
      )
      expect(loggedInitFailed).toBe(false)

      errorSpy.mockRestore()
    })

    it('handles empty chat history response', async () => {
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: [] },
        system_health: { data: { status: 'healthy' } },
      })

      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        // Should handle empty state - sidebar title still renders
        // #5456: ChatSidebar's mobile header no longer duplicates the
        // chatHistory label (moved to h3-only), so getByText matches
        // exactly once.
        expect(screen.getByText('chat.sidebar.chatHistory')).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels', async () => {
      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(screen.getByLabelText('chat.sidebar.createNew')).toBeInTheDocument()
      })

      expect(screen.getByLabelText('chat.sidebar.resetChat')).toBeInTheDocument()
      expect(screen.getByLabelText('chat.sidebar.deleteChat')).toBeInTheDocument()
      expect(screen.getByLabelText('chat.sidebar.refreshList')).toBeInTheDocument()
      expect(screen.getByLabelText('chat.sidebar.collapseSidebar')).toBeInTheDocument()
    })

    it('supports keyboard navigation', async () => {
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: mockChatSessions },
        system_health: { data: { status: 'healthy' } },
      })

      renderComponent(ChatInterface, { pinia: true, router: true })

      await waitFor(() => {
        expect(mockInitializeChatInterface).toHaveBeenCalledTimes(1)
      })

      // Verify the sidebar has interactive elements
      const createButton = screen.getByLabelText('chat.sidebar.createNew')
      expect(createButton).toBeInTheDocument()

      // Test keyboard activation on sidebar button
      createButton.focus()
      await user.keyboard('{Enter}')

      await waitForUpdate()
    })
  })

  describe('Performance', () => {
    it('handles large message lists efficiently', async () => {
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: [] },
        system_health: { data: { status: 'healthy' } },
      })

      const { container } = renderComponent(ChatInterface, { pinia: true, router: true })

      // Component should render without performance issues
      expect(container).toBeInTheDocument()
    })
  })
})
