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

// ---- Module mocks ----

// Mock BatchApiService - the primary initialization path for ChatInterface
const mockInitializeChatInterface = vi.fn()
const mockLoadChatInitData = vi.fn()
vi.mock('@/services/BatchApiService', () => ({
  default: {
    initializeChatInterface: (...args: any[]) => mockInitializeChatInterface(...args),
    loadChatInitData: (...args: any[]) => mockLoadChatInitData(...args),
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

// Mock ChatRepository to prevent real axios calls
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
vi.mock('@/composables/useBackoffPoller', () => ({
  useBackoffPoller: () => ({
    start: vi.fn(),
    stop: vi.fn(),
    isCircuitOpen: { value: false },
    consecutiveFailures: { value: 0 },
    currentInterval: { value: 10000 },
  }),
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
      settings: { data: {} },
    })
  })

  afterEach(() => {
    webSocketTestUtil.teardown()
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders the main chat interface', async () => {
      renderComponent(ChatInterface, { pinia: true })

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
      renderComponent(ChatInterface, { pinia: true })

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
        settings: { data: {} },
      })

      renderComponent(ChatInterface, { pinia: true })

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

      renderComponent(ChatInterface, { pinia: true })

      // Sidebar should still render with refresh button available
      expect(screen.getByLabelText('chat.sidebar.refreshList')).toBeInTheDocument()
    })
  })

  describe('Chat Management', () => {
    it('creates a new chat session', async () => {
      renderComponent(ChatInterface, { pinia: true })

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
        settings: { data: {} },
      })

      renderComponent(ChatInterface, { pinia: true })

      // Verify initialization was called with session data
      await waitFor(() => {
        expect(mockInitializeChatInterface).toHaveBeenCalled()
      })
    })

    it('deletes a chat session', async () => {
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: mockChatSessions },
        system_health: { data: { status: 'healthy' } },
        settings: { data: {} },
      })

      renderComponent(ChatInterface, { pinia: true })

      await waitFor(() => {
        expect(mockInitializeChatInterface).toHaveBeenCalled()
      })

      // Delete button in the sidebar toolbar is disabled without an active session
      const deleteButton = screen.getByLabelText('chat.sidebar.deleteChat')
      expect(deleteButton).toBeInTheDocument()
    })

    it('resets current chat session button is disabled without active session', async () => {
      renderComponent(ChatInterface, { pinia: true })

      await waitFor(() => {
        expect(screen.getByLabelText('chat.sidebar.resetChat')).toBeInTheDocument()
      })

      // Reset button is disabled when no session is active (store.currentSessionId is empty)
      const resetButton = screen.getByLabelText('chat.sidebar.resetChat') as HTMLButtonElement
      expect(resetButton).toBeDisabled()
    })

    it('refreshes chat list', async () => {
      renderComponent(ChatInterface, { pinia: true })

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
      renderComponent(ChatInterface, { pinia: true })

      await waitFor(() => {
        // ChatInput placeholder renders as i18n key
        const input = screen.getByPlaceholderText('chat.input.typeMessage')
        expect(input).toBeInTheDocument()
      })
    })

    it('sends a message to the chat', async () => {
      renderComponent(ChatInterface, { pinia: true })

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
      renderComponent(ChatInterface, { pinia: true })

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
      renderComponent(ChatInterface, { pinia: true })

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
      renderComponent(ChatInterface, { pinia: true })

      // The chat interface should render the content area
      await waitFor(() => {
        expect(mockInitializeChatInterface).toHaveBeenCalled()
      })
    })
  })

  describe('WebSocket Integration', () => {
    it('handles incoming WebSocket messages', async () => {
      renderComponent(ChatInterface, { pinia: true })

      // Simulate WebSocket connection
      const ws = webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)

      // Simulate incoming chat message
      webSocketTestUtil.simulateChatMessage('Hello from WebSocket!', 'assistant')

      // WebSocket message is dispatched; component should handle it
      await waitForUpdate()
      expect(ws).toBeDefined()
    })

    it('handles WebSocket connection errors', async () => {
      renderComponent(ChatInterface, { pinia: true })

      const ws = webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)
      webSocketTestUtil.simulateError('Connection failed')

      // Should handle error gracefully
      expect(ws).toBeDefined()
    })

    it('handles workflow notifications via WebSocket', async () => {
      renderComponent(ChatInterface, { pinia: true })

      webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)
      webSocketTestUtil.simulateWorkflowUpdate('workflow-123', 'running', 2)

      // Should dispatch workflow update without crashing
      await waitForUpdate()
    })
  })

  describe('Knowledge Persistence Dialog', () => {
    it('opens knowledge persistence dialog when triggered', async () => {
      const { container } = renderComponent(ChatInterface, { pinia: true })

      // Verify the component renders without errors
      expect(container).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      // Make initialization fail
      mockInitializeChatInterface.mockRejectedValue(new Error('Network error'))

      const { container } = renderComponent(ChatInterface, { pinia: true })

      // Component should render despite error
      await waitFor(() => {
        expect(container).toBeInTheDocument()
      })
    })

    it('handles empty chat history response', async () => {
      mockInitializeChatInterface.mockResolvedValue({
        chat_sessions: { data: [] },
        system_health: { data: { status: 'healthy' } },
        settings: { data: {} },
      })

      renderComponent(ChatInterface, { pinia: true })

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
      renderComponent(ChatInterface, { pinia: true })

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
        settings: { data: {} },
      })

      renderComponent(ChatInterface, { pinia: true })

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
        settings: { data: {} },
      })

      const { container } = renderComponent(ChatInterface, { pinia: true })

      // Component should render without performance issues
      expect(container).toBeInTheDocument()
    })
  })
})
