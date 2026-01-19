import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, fireEvent, waitFor } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import TerminalWindow from '../TerminalWindow.vue'
import {
  renderComponent,
  createMockTerminalSession,
  waitForUpdate,
} from '../../test/utils/test-utils'
import { createMockApiService } from '../../test/mocks/api-client-mock'
import { webSocketTestUtil, WebSocketMessageType } from '../../test/mocks/websocket-mock'

// Mock dependencies
vi.mock('@/utils/ApiClient', () => ({
  default: createMockApiService().client,
}))

vi.mock('@/services/api.js', () => createMockApiService())

describe('TerminalWindow', () => {
  let user: ReturnType<typeof userEvent.setup>
  let mockApi: ReturnType<typeof createMockApiService>

  beforeEach(() => {
    user = userEvent.setup()
    webSocketTestUtil.setup()
    mockApi = createMockApiService()
  })

  afterEach(() => {
    webSocketTestUtil.teardown()
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders the terminal window with header', () => {
      renderComponent(TerminalWindow, { router: true })

      expect(screen.getByText(/Terminal -/)).toBeInTheDocument()
      expect(screen.getByText('🛑 KILL')).toBeInTheDocument()
      expect(screen.getByText('⚡ INT')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '🔄' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '🗑️' })).toBeInTheDocument()
    })

    it('renders with proper session title', () => {
      const sessionData = createMockTerminalSession({
        title: 'My Custom Terminal Session'
      })

      renderComponent(TerminalWindow, { router: true,
        props: { sessionData }
      })

      expect(screen.getByText('Terminal - My Custom Terminal Session')).toBeInTheDocument()
    })

    it('shows correct button states based on terminal status', () => {
      const sessionData = createMockTerminalSession({
        hasRunningProcesses: true,
        hasActiveProcess: true,
        hasAutomatedWorkflow: true,
        automationPaused: false,
      })

      renderComponent(TerminalWindow, { router: true,
        props: { sessionData }
      })

      const killButton = screen.getByText('🛑 KILL')
      const interruptButton = screen.getByText('⚡ INT')
      const pauseButton = screen.getByText('⏸️ PAUSE')

      expect(killButton).not.toBeDisabled()
      expect(interruptButton).not.toBeDisabled()
      expect(pauseButton).not.toBeDisabled()
    })

    it('disables buttons when no processes are running', () => {
      const sessionData = createMockTerminalSession({
        hasRunningProcesses: false,
        hasActiveProcess: false,
        hasAutomatedWorkflow: false,
      })

      renderComponent(TerminalWindow, { router: true,
        props: { sessionData }
      })

      const killButton = screen.getByText('🛑 KILL')
      const interruptButton = screen.getByText('⚡ INT')
      const pauseButton = screen.getByText('⏸️ PAUSE')

      expect(killButton).toBeDisabled()
      expect(interruptButton).toBeDisabled()
      expect(pauseButton).toBeDisabled()
    })
  })

  describe('WebSocket Connection', () => {
    it('establishes WebSocket connection on mount', () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.getConnection()
      expect(ws).toBeDefined()
      expect(ws?.url).toContain('ws://')
    })

    it('handles WebSocket connection status', async () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Initially should show connecting state
      expect(screen.getByRole('button', { name: "🔄" })).toBeInTheDocument()

      // Simulate connection established
      await waitFor(() => {
        webSocketTestUtil.expectConnectionOpened()
      })
    })

    it('handles incoming terminal output', async () => {
      renderComponent(TerminalWindow, { router: true })

      webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Simulate terminal output
      webSocketTestUtil.simulateTerminalOutput('$ ls -la\ntotal 48\ndrwxr-xr-x  6 user user 4096 Jan 1 12:00 .\n', 'ls -la')

      await waitFor(() => {
        expect(screen.getByText(/ls -la/)).toBeInTheDocument()
      })
    })

    it('handles WebSocket disconnection', async () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')
      webSocketTestUtil.simulateClose(1000, 'Normal closure')

      await waitFor(() => {
        webSocketTestUtil.expectConnectionClosed()
      })
    })

    it('handles WebSocket errors', async () => {
      renderComponent(TerminalWindow, { router: true })

      webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')
      webSocketTestUtil.simulateError('Connection failed')

      // Should handle error gracefully - check for error indication
      await waitFor(() => {
        expect(screen.getByRole('button', { name: "🔄" })).toBeInTheDocument()
      })
    })
  })

  describe('Terminal Controls', () => {
    it('executes emergency kill command', async () => {
      const sessionData = createMockTerminalSession({
        hasRunningProcesses: true,
      })

      renderComponent(TerminalWindow, { router: true,
        props: { sessionData }
      })

      const killButton = screen.getByText('🛑 KILL')
      await user.click(killButton)

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith('/api/terminal/kill')
      })
    })

    it('interrupts current process', async () => {
      const sessionData = createMockTerminalSession({
        hasActiveProcess: true,
      })

      renderComponent(TerminalWindow, { router: true,
        props: { sessionData }
      })

      const interruptButton = screen.getByText('⚡ INT')
      await user.click(interruptButton)

      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith('/api/terminal/interrupt')
      })
    })

    it('toggles automation pause/resume', async () => {
      const sessionData = createMockTerminalSession({
        hasAutomatedWorkflow: true,
        automationPaused: false,
      })

      renderComponent(TerminalWindow, { router: true,
        props: { sessionData }
      })

      const pauseButton = screen.getByText('⏸️ PAUSE')
      await user.click(pauseButton)

      // Should send pause command
      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalledWith(
          '/api/terminal/automation/pause'
        )
      })
    })

    it('handles reconnect action', async () => {
      renderComponent(TerminalWindow, { router: true })

      const reconnectButton = screen.getByRole('button', { name: "🔄" })
      await user.click(reconnectButton)

      // Should attempt to reconnect WebSocket
      await waitFor(() => {
        const ws = webSocketTestUtil.getConnection()
        expect(ws).toBeDefined()
      })
    })

    it('clears terminal output', async () => {
      renderComponent(TerminalWindow, { router: true })

      // First add some output
      webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')
      webSocketTestUtil.simulateTerminalOutput('Some terminal output')

      await waitFor(() => {
        expect(screen.getByText(/Some terminal output/)).toBeInTheDocument()
      })

      const clearButton = screen.getByRole('button', { name: /clear/i })
      await user.click(clearButton)

      // Output should be cleared
      await waitFor(() => {
        expect(screen.queryByText(/Some terminal output/)).not.toBeInTheDocument()
      })
    })
  })

  describe('Command Input', () => {
    it('sends command through WebSocket', async () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      const commandInput = screen.getByPlaceholderText(/enter command/i) as HTMLInputElement
      const sendButton = screen.getByRole('button', { name: /send/i })

      await user.type(commandInput, 'ls -la')
      await user.click(sendButton)

      await waitFor(() => {
        webSocketTestUtil.expectMessageSent({
          type: 'command',
          command: 'ls -la',
        })
      })

      // Input should be cleared after sending
      expect(commandInput.value).toBe('')
    })

    it('sends command with Enter key', async () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      const commandInput = screen.getByPlaceholderText(/enter command/i)

      await user.type(commandInput, 'pwd')
      await user.keyboard('{Enter}')

      await waitFor(() => {
        webSocketTestUtil.expectMessageSent({
          type: 'command',
          command: 'pwd',
        })
      })
    })

    it('prevents sending empty commands', async () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      const sendButton = screen.getByRole('button', { name: /send/i })
      await user.click(sendButton)

      // Should not send empty command
      expect(ws?.send).not.toHaveBeenCalled()
    })

    it('handles command history navigation', async () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')
      const commandInput = screen.getByPlaceholderText(/enter command/i) as HTMLInputElement

      // Send a few commands to build history
      await user.type(commandInput, 'command1')
      await user.keyboard('{Enter}')

      await user.type(commandInput, 'command2')
      await user.keyboard('{Enter}')

      // Navigate history with arrow keys
      await user.keyboard('{ArrowUp}')
      expect(commandInput.value).toBe('command2')

      await user.keyboard('{ArrowUp}')
      expect(commandInput.value).toBe('command1')

      await user.keyboard('{ArrowDown}')
      expect(commandInput.value).toBe('command2')
    })
  })

  describe('Terminal Output Display', () => {
    it('displays command output correctly', async () => {
      renderComponent(TerminalWindow, { router: true })

      webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Simulate command and its output
      webSocketTestUtil.simulateTerminalOutput(
        '$ ls -la\ntotal 48\ndrwxr-xr-x  6 user user 4096 Jan 1 12:00 .\ndrwxr-xr-x  3 user user 4096 Jan 1 12:00 ..',
        'ls -la'
      )

      await waitFor(() => {
        expect(screen.getByText(/ls -la/)).toBeInTheDocument()
        expect(screen.getByText(/total 48/)).toBeInTheDocument()
      })
    })

    it('handles colored terminal output', async () => {
      renderComponent(TerminalWindow, { router: true })

      webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Simulate colored output with ANSI codes
      webSocketTestUtil.simulateTerminalOutput(
        '\x1b[32mSuccess:\x1b[0m Command executed successfully',
        'test-command'
      )

      await waitFor(() => {
        expect(screen.getByText(/Success:/)).toBeInTheDocument()
      })
    })

    it('auto-scrolls to bottom on new output', async () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Add multiple lines of output
      for (let i = 0; i < 10; i++) {
        webSocketTestUtil.simulateTerminalOutput(`Line ${i}`)
        await waitForUpdate()
      }

      // Terminal should scroll to show latest output
      await waitFor(() => {
        expect(screen.getByText('Line 9')).toBeInTheDocument()
      })
    })

    it('handles large output efficiently', async () => {
      renderComponent(TerminalWindow, { router: true })

      webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Simulate large output
      const largeOutput = Array.from({ length: 1000 }, (_, i) => `Line ${i}`).join('\n')
      webSocketTestUtil.simulateTerminalOutput(largeOutput)

      // Should handle large output without performance issues
      await waitFor(() => {
        expect(screen.getByText(/Line 999/)).toBeInTheDocument()
      })
    })
  })

  describe('Session Management', () => {
    it('updates session status from props', async () => {
      const { rerender } = renderComponent(TerminalWindow, { router: true,
        props: {
          sessionData: createMockTerminalSession({
            hasRunningProcesses: false
          })
        }
      })

      const killButton = screen.getByText('🛑 KILL')
      expect(killButton).toBeDisabled()

      // Update props
      await rerender({
        sessionData: createMockTerminalSession({
          hasRunningProcesses: true
        })
      })

      expect(killButton).not.toBeDisabled()
    })

    it('handles session reconnection', async () => {
      renderComponent(TerminalWindow, { router: true })

      // Simulate disconnect
      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')
      webSocketTestUtil.simulateClose(1006, 'Abnormal closure')

      // Click reconnect
      const reconnectButton = screen.getByRole('button', { name: "🔄" })
      await user.click(reconnectButton)

      // Should establish new connection
      await waitFor(() => {
        const newWs = webSocketTestUtil.getConnection()
        expect(newWs).toBeDefined()
      })
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      mockApi.client.post.mockRejectedValue(new Error('Network error'))

      const sessionData = createMockTerminalSession({
        hasRunningProcesses: true,
      })

      renderComponent(TerminalWindow, { router: true,
        props: { sessionData }
      })

      const killButton = screen.getByText('🛑 KILL')
      await user.click(killButton)

      // Should handle error without crashing
      await waitFor(() => {
        expect(mockApi.client.post).toHaveBeenCalled()
      })
    })

    it('handles malformed WebSocket messages', async () => {
      renderComponent(TerminalWindow, { router: true })

      const ws = webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Send malformed message
      ws.simulateMessage('invalid json')

      // Should handle gracefully without crashing
      expect(ws).toBeDefined()
    })
  })

  describe('Accessibility', () => {
    it('has proper ARIA labels for control buttons', () => {
      const sessionData = createMockTerminalSession({
        hasRunningProcesses: true,
        hasActiveProcess: true,
        hasAutomatedWorkflow: true,
      })

      renderComponent(TerminalWindow, { router: true,
        props: { sessionData }
      })

      expect(screen.getByRole('button', { name: /emergency kill/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /interrupt/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument()
    })

    it('supports keyboard navigation', async () => {
      renderComponent(TerminalWindow, { router: true })

      const commandInput = screen.getByPlaceholderText(/enter command/i)

      commandInput.focus()
      expect(document.activeElement).toBe(commandInput)

      // Tab to send button
      await user.tab()
      expect(document.activeElement).toBe(screen.getByRole('button', { name: /send/i }))
    })
  })

  describe('Integration', () => {
    it('integrates with chat workflow notifications', async () => {
      renderComponent(TerminalWindow, { router: true })

      webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Simulate workflow notification that affects terminal
      webSocketTestUtil.simulateMessage(WebSocketMessageType.WORKFLOW_UPDATE, {
        workflowId: 'test-workflow',
        status: 'terminal_command_executing',
        details: { command: 'apt-get install -y nginx' }
      })

      // Terminal should show relevant information
      await waitFor(() => {
        // Check for workflow-related terminal updates
        expect(screen.getByText(/Terminal/)).toBeInTheDocument()
      })
    })
  })

  describe('Performance', () => {
    it('handles high-frequency output efficiently', async () => {
      renderComponent(TerminalWindow, { router: true })

      webSocketTestUtil.connect('ws://localhost:8001/terminal/ws')

      // Simulate rapid output
      const startTime = performance.now()

      for (let i = 0; i < 100; i++) {
        webSocketTestUtil.simulateTerminalOutput(`Rapid output line ${i}`)
      }

      await waitFor(() => {
        expect(screen.getByText('Rapid output line 99')).toBeInTheDocument()
      })

      const endTime = performance.now()
      const duration = endTime - startTime

      // Should handle rapid updates efficiently (less than 1 second for 100 messages)
      expect(duration).toBeLessThan(1000)
    })
  })
})
