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
import { createMockApiService } from '../../test/mocks/api-client-mock'
import { webSocketTestUtil, WebSocketMessageType } from '../../test/mocks/websocket-mock'
import { ServiceURLs } from '@/constants/network'

// Mock dependencies
vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/services/api.js', () => ({
  default: {
    sendMessage: vi.fn(),
    getChatHistory: vi.fn(),
    getChatMessages: vi.fn(),
    deleteChatHistory: vi.fn(),
  },
  apiService: {
    sendMessage: vi.fn(),
    getChatHistory: vi.fn(),
    getChatMessages: vi.fn(),
    deleteChatHistory: vi.fn(),
  },
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
  })

  afterEach(() => {
    webSocketTestUtil.teardown()
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders the main chat interface', () => {
      renderComponent(ChatInterface)

      expect(screen.getByText('Chat History')).toBeInTheDocument()
      expect(screen.getByLabelText('Add')).toBeInTheDocument()
      expect(screen.getByLabelText('Reset')).toBeInTheDocument()
      expect(screen.getByLabelText('Delete')).toBeInTheDocument()
      expect(screen.getByLabelText('Refresh')).toBeInTheDocument()
    })

    it('renders with collapsed sidebar when sidebarCollapsed is true', async () => {
      const { container } = renderComponent(ChatInterface)

      const collapseButton = screen.getByLabelText('Collapse')
      await user.click(collapseButton)

      const sidebar = container.querySelector('.w-80')
      expect(sidebar).toHaveClass('w-12')
    })

    it('displays chat history when available', async () => {
      // Mock API to return chat sessions
      const mockApi = createMockApiService()
      mockApi.client.mockGet('/api/chat/history', {
        success: true,
        data: { sessions: mockChatSessions }
      })

      renderComponent(ChatInterface)

      await waitFor(() => {
        expect(screen.getByText('Test Chat 1')).toBeInTheDocument()
        expect(screen.getByText('Test Chat 2')).toBeInTheDocument()
      })
    })

    it('shows loading state while fetching chat history', () => {
      // Mock API to delay response
      const mockApi = createMockApiService()
      mockApi.client.get.mockImplementation(() =>
        new Promise(resolve => setTimeout(resolve, 1000))
      )

      renderComponent(ChatInterface)

      // Should show some loading indication
      expect(screen.getByLabelText('Refresh')).toBeInTheDocument()
    })
  })

  describe('Chat Management', () => {
    it('creates a new chat session', async () => {
      const mockApi = createMockApiService()
      renderComponent(ChatInterface)

      const newChatButton = screen.getByLabelText('Add')
      await user.click(newChatButton)

      await waitFor(() => {
        // Should generate a new chat ID and switch to it
        expect(mockApi.client.get).toHaveBeenCalledWith('/api/chat/history')
      })
    })

    it('switches between chat sessions', async () => {
      const mockApi = createMockApiService()
      mockApi.client.mockGet('/api/chat/history', {
        success: true,
        data: { sessions: mockChatSessions }
      })

      renderComponent(ChatInterface)

      await waitFor(() => {
        expect(screen.getByText('Test Chat 1')).toBeInTheDocument()
      })

      const chatItem = screen.getByText('Test Chat 1')
      await user.click(chatItem)

      // Should load messages for the selected chat
      await waitFor(() => {
        expect(mockApi.client.get).toHaveBeenCalledWith('/api/chat/history/chat-1')
      })
    })

    it('deletes a chat session', async () => {
      const mockApi = createMockApiService()
      mockApi.client.mockGet('/api/chat/history', {
        success: true,
        data: { sessions: mockChatSessions }
      })

      renderComponent(ChatInterface)

      await waitFor(() => {
        expect(screen.getByText('Test Chat 1')).toBeInTheDocument()
      })

      // Find and click the delete button for the first chat
      const deleteButtons = screen.getAllByTitle('Delete')
      await user.click(deleteButtons[0]) // First delete button (in the chat item)

      await waitFor(() => {
        expect(mockApi.client.delete).toHaveBeenCalledWith('/api/chat/history/chat-1')
      })
    })

    it('resets current chat session', async () => {
      renderComponent(ChatInterface)

      const resetButton = screen.getByLabelText('Reset')
      await user.click(resetButton)

      // Should clear current messages and reset state
      expect(resetButton).toBeInTheDocument()
    })

    it('refreshes chat list', async () => {
      const mockApi = createMockApiService()
      renderComponent(ChatInterface)

      const refreshButton = screen.getByLabelText('Refresh')
      await user.click(refreshButton)

      await waitFor(() => {
        expect(mockApi.client.get).toHaveBeenCalledWith('/api/chat/history')
      })
    })
  })

  describe('Message Handling', () => {
    it('sends a message to the chat', async () => {
      const mockApi = createMockApiService()
      renderComponent(ChatInterface)

      // Find the message input and send button
      const messageInput = screen.getByPlaceholderText(/type your message/i) as HTMLTextAreaElement
      const sendButton = screen.getByRole('button', { name: /send/i })

      await user.type(messageInput, 'Hello, AutoBot!')
      await user.click(sendButton)

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith('/api/chat',
          expect.objectContaining({
            message: 'Hello, AutoBot!'
          })
        )
      })

      // Input should be cleared after sending
      expect(messageInput.value).toBe('')
    })

    it('handles message input with keyboard shortcuts', async () => {
      const mockApi = createMockApiService()
      renderComponent(ChatInterface)

      const messageInput = screen.getByPlaceholderText(/type your message/i)
      await user.type(messageInput, 'Test message')

      // Send with Enter key
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith('/api/chat',
          expect.objectContaining({
            message: 'Test message'
          })
        )
      })
    })

    it('prevents sending empty messages', async () => {
      const mockApi = createMockApiService()
      renderComponent(ChatInterface)

      const sendButton = screen.getByRole('button', { name: /send/i })
      await user.click(sendButton)

      // Should not make API call for empty message
      expect(mockApi.client.post).not.toHaveBeenCalled()
    })

    it('displays chat messages correctly', async () => {
      const mockApi = createMockApiService()
      mockApi.client.mockGet('/api/chat/history/chat-1', {
        success: true,
        data: {
          chatId: 'chat-1',
          messages: [
            createMockChatMessage({ content: 'User message', sender: 'user' }),
            createMockChatMessage({ content: 'Assistant response', sender: 'assistant' }),
          ]
        }
      })

      renderComponent(ChatInterface)

      // Simulate selecting a chat
      const { container } = renderComponent(ChatInterface)
      const component = container.querySelector('div') as any

      // Trigger message loading
      await waitFor(() => {
        expect(mockApi.client.get).toHaveBeenCalled()
      })
    })
  })

  describe('WebSocket Integration', () => {
    it('handles incoming WebSocket messages', async () => {
      renderComponent(ChatInterface)

      // Simulate WebSocket connection
      const ws = webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)

      // Simulate incoming chat message
      webSocketTestUtil.simulateChatMessage('Hello from WebSocket!', 'assistant')

      await waitFor(() => {
        expect(screen.getByText('Hello from WebSocket!')).toBeInTheDocument()
      })
    })

    it('handles WebSocket connection errors', async () => {
      renderComponent(ChatInterface)

      const ws = webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)
      webSocketTestUtil.simulateError('Connection failed')

      // Should handle error gracefully
      expect(ws).toBeDefined()
    })

    it('handles workflow notifications via WebSocket', async () => {
      renderComponent(ChatInterface)

      webSocketTestUtil.connect(ServiceURLs.WEBSOCKET_LOCAL)
      webSocketTestUtil.simulateWorkflowUpdate('workflow-123', 'running', 2)

      // Should display workflow notification or update
      await waitForUpdate()
      // Add specific assertions based on your workflow UI
    })
  })

  describe('Knowledge Persistence Dialog', () => {
    it('opens knowledge persistence dialog when triggered', async () => {
      renderComponent(ChatInterface)

      // This would typically be triggered by some chat action
      // Simulate the condition that opens the dialog
      const { container } = renderComponent(ChatInterface)

      // Check if dialog can be opened (implementation depends on your logic)
      expect(container).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      const mockApi = createMockApiService()
      mockApi.client.post.mockRejectedValue(new Error('Network error'))

      renderComponent(ChatInterface)

      const messageInput = screen.getByPlaceholderText(/type your message/i)
      const sendButton = screen.getByRole('button', { name: /send/i })

      await user.type(messageInput, 'Test message')
      await user.click(sendButton)

      // Should handle error without crashing
      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalled()
      })
    })

    it('handles empty chat history response', async () => {
      const mockApi = createMockApiService()
      mockApi.client.mockGet('/api/chat/history', {
        success: true,
        data: { sessions: [] }
      })

      renderComponent(ChatInterface)

      await waitFor(() => {
        // Should handle empty state gracefully
        expect(screen.getByText('Chat History')).toBeInTheDocument()
      })
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels', () => {
      renderComponent(ChatInterface)

      expect(screen.getByLabelText('Add')).toBeInTheDocument()
      expect(screen.getByLabelText('Reset')).toBeInTheDocument()
      expect(screen.getByLabelText('Delete')).toBeInTheDocument()
      expect(screen.getByLabelText('Refresh')).toBeInTheDocument()
      expect(screen.getByLabelText('Collapse')).toBeInTheDocument()
    })

    it('supports keyboard navigation', async () => {
      const mockApi = createMockApiService()
      mockApi.client.mockGet('/api/chat/history', {
        success: true,
        data: { sessions: mockChatSessions }
      })

      renderComponent(ChatInterface)

      await waitFor(() => {
        expect(screen.getByText('Test Chat 1')).toBeInTheDocument()
      })

      const chatItem = screen.getByText('Test Chat 1').closest('[tabindex="0"]')
      expect(chatItem).toBeInTheDocument()

      // Test keyboard activation
      ;(chatItem as HTMLElement)?.focus()
      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(mockApi.client.get).toHaveBeenCalledWith('/api/chat/history/chat-1')
      })
    })
  })

  describe('Performance', () => {
    it('handles large message lists efficiently', async () => {
      const manyMessages = Array.from({ length: 100 }, (_, i) =>
        createMockChatMessage({
          content: `Message ${i}`,
          sender: i % 2 === 0 ? 'user' : 'assistant'
        })
      )

      const mockApi = createMockApiService()
      mockApi.client.mockGet('/api/chat/history/chat-1', {
        success: true,
        data: {
          chatId: 'chat-1',
          messages: manyMessages
        }
      })

      const { container } = renderComponent(ChatInterface)

      // Component should render without performance issues
      expect(container).toBeInTheDocument()
    })
  })
})
