// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/vue'
import userEvent from '@testing-library/user-event'
import { ref, reactive } from 'vue'
import TerminalWindow from '../terminal/TerminalWindow.vue'
import {
  renderComponent,
} from '../../test/utils/test-utils'
import { webSocketTestUtil } from '../../test/mocks/websocket-mock'

// ---- Mock dependencies ----
// Vitest 4 hoists vi.mock factories above imports, so inline vi.fn()
// calls are used instead of referencing external helpers (#2676).

vi.mock('@/utils/ApiClient', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  },
}))

vi.mock('@/services/api', () => ({
  default: {
    sendMessage: vi.fn(),
    executeCommand: vi.fn(),
    interruptProcess: vi.fn(),
    killAllProcesses: vi.fn(),
  },
  apiService: {
    sendMessage: vi.fn(),
    executeCommand: vi.fn(),
    interruptProcess: vi.fn(),
    killAllProcesses: vi.fn(),
  },
}))

// Capture mock functions so tests can assert on them (#2641)
const mockSendInput = vi.fn()
const mockSendSignal = vi.fn()
const mockIsConnected = vi.fn(() => false)
const mockConnect = vi.fn().mockResolvedValue(undefined)
const mockDisconnect = vi.fn()
const mockCreateSession = vi.fn().mockResolvedValue('test-session-id')
const mockCloseSession = vi.fn().mockResolvedValue(undefined)
const mockResize = vi.fn()

vi.mock('@/services/TerminalService', () => ({
  useTerminalService: vi.fn(() => ({
    sendInput: mockSendInput,
    sendStdin: vi.fn(),
    sendTabCompletion: vi.fn(),
    sendHistoryGet: vi.fn(),
    sendHistorySearch: vi.fn(),
    sendSignal: mockSendSignal,
    resize: mockResize,
    isConnected: mockIsConnected,
    sessions: reactive(new Map()),
    connectionStatus: ref('disconnected'),
    createSession: mockCreateSession,
    connect: mockConnect,
    disconnect: mockDisconnect,
    closeSession: mockCloseSession,
  })),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  }),
}))

// i18n messages that match the actual en.json terminal.window namespace
const _terminalI18nMessages = {
  en: {
    terminal: {
      window: {
        titlePrefix: 'Terminal -',
        defaultTitle: 'Terminal',
        emergencyKillTitle: 'EMERGENCY KILL - Stop all running processes immediately',
        resumeAutomation: 'Resume automated workflow',
        pauseAutomation: 'Pause automation and take manual control',
        interruptProcess: 'Send Ctrl+C to interrupt current process',
        reconnect: 'Reconnect',
        clear: 'Clear',
        closeWindow: 'Close Window',
        session: 'Session:',
        lines: 'Lines:',
        shortcutHint: 'Press Ctrl+C to interrupt, Ctrl+D to exit',
        startExampleWorkflowTitle: 'Start Example Automated Workflow (for testing)',
        testWorkflow: 'Test Workflow',
        downloadLogTitle: 'Download Session Log',
        saveLog: 'Save Log',
        shareSessionTitle: 'Share Session',
        share: 'Share',
        connectionLost: 'Connection Lost',
        connectionLostMessage: 'The terminal connection was lost. Would you like to reconnect?',
        cancel: 'Cancel',
        destructiveCommand: 'Potentially Destructive Command',
        commandToExecute: 'Command to execute:',
        riskLevel: 'Risk Level:',
        commandMay: 'This command may:',
        riskDeleteFiles: 'Delete files or directories permanently',
        riskModifyConfig: 'Modify system configurations',
        riskChangePermissions: 'Change file permissions or ownership',
        riskInstallRemove: 'Install or remove software packages',
        confirmProceed: 'Are you sure you want to proceed?',
        emergencyKillAllProcesses: 'Emergency Kill All Processes',
        emergencyKillWarning: 'WARNING: This will immediately terminate ALL running processes in this terminal session!',
        runningProcesses: 'Running processes:',
        cannotBeUndone: 'This action cannot be undone. Continue?',
        workflowStepConfirmation: 'AI Workflow Step Confirmation',
        aiWantsToExecute: 'The AI wants to execute the following command:',
        chooseAction: 'Choose your action:',
        executeLabel: 'Execute:',
        executeDesc: 'Run this command and continue to next step',
        skipLabel: 'Skip:',
        skipDesc: 'Skip this command and continue to next step',
        takeControlLabel: 'Take Control:',
        takeControlDesc: 'Pause automation and perform manual steps',
        noStepData: 'No step data available.',
        stepProgress: 'Step {current} of {total}',
        statusConnected: 'Connected',
        statusConnecting: 'Connecting...',
        statusDisconnected: 'Disconnected',
        statusError: 'Error',
        statusUnknown: 'Unknown',
      },
    },
  },
}

// Stub child components that use i18n or other plugins
const renderTerminal = (options: Record<string, unknown> = {}) => {
  return renderComponent(TerminalWindow, {
    router: true,
    global: {
      stubs: {
        AdvancedStepConfirmationModal: { template: '<div data-testid="step-modal-stub" />' },
        CompletionSuggestions: { template: '<div data-testid="completion-stub" />' },
      },
    },
    ...options,
  })
}

describe('TerminalWindow', () => {
  let user: ReturnType<typeof userEvent.setup>

  beforeEach(() => {
    user = userEvent.setup()
    webSocketTestUtil.setup()

    // Reset mock function state
    mockSendInput.mockClear()
    mockSendSignal.mockClear()
    mockIsConnected.mockReturnValue(false)
    mockConnect.mockClear().mockResolvedValue(undefined)
    mockDisconnect.mockClear()
    mockCreateSession.mockClear().mockResolvedValue('test-session-id')
    mockCloseSession.mockClear().mockResolvedValue(undefined)
    mockResize.mockClear()
  })

  afterEach(() => {
    webSocketTestUtil.teardown()
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders the terminal window with header', () => {
      renderTerminal()

      // i18n keys are returned as-is since no messages are loaded in the
      // default test i18n; check for the key fallback text
      expect(screen.getByText(/terminal\.window\.titlePrefix/)).toBeInTheDocument()
      expect(screen.getByText(/🛑 KILL/)).toBeInTheDocument()
      expect(screen.getByText(/⚡ INT/)).toBeInTheDocument()
      expect(screen.getByText('🔄')).toBeInTheDocument()
      expect(screen.getByText('🗑️')).toBeInTheDocument()
    })

    it('renders the status bar with session info', () => {
      renderTerminal()

      // Status bar shows disconnected state and session info
      expect(screen.getByText(/terminal\.window\.statusDisconnected/)).toBeInTheDocument()
      expect(screen.getByText(/terminal\.window\.session/)).toBeInTheDocument()
      expect(screen.getByText(/terminal\.window\.lines/)).toBeInTheDocument()
    })

    it('renders control buttons in disabled state initially', () => {
      renderTerminal()

      // Kill button disabled because no running processes
      const killButton = screen.getByText(/🛑 KILL/)
      expect(killButton.closest('button')).toBeDisabled()

      // Interrupt button disabled because no active process
      const intButton = screen.getByText(/⚡ INT/)
      expect(intButton.closest('button')).toBeDisabled()

      // Pause button disabled because no automated workflow
      const pauseButton = screen.getByText(/⏸️ PAUSE/)
      expect(pauseButton.closest('button')).toBeDisabled()
    })

    it('renders the terminal input area', () => {
      renderTerminal()

      // The input element exists with class terminal-input
      const input = document.querySelector('.terminal-input') as HTMLInputElement
      expect(input).not.toBeNull()
      // Input is disabled when not connected
      expect(input).toBeDisabled()
    })

    it('renders the footer with action buttons', () => {
      renderTerminal()

      // Footer buttons for workflow test, save log, share
      expect(screen.getByText(/terminal\.window\.saveLog/)).toBeInTheDocument()
      expect(screen.getByText(/terminal\.window\.share/)).toBeInTheDocument()
    })
  })

  describe('Connection Lifecycle', () => {
    it('calls connect on the terminal service during mount', async () => {
      renderTerminal()

      // The component calls connect() in onMounted, which invokes
      // the mocked connectToService from useTerminalService
      await waitFor(() => {
        expect(mockConnect).toHaveBeenCalled()
      })
    })

    it('shows the reconnect button in the header', () => {
      renderTerminal()

      // The reconnect button shows 🔄 when not connecting
      const reconnectButton = screen.getByText('🔄')
      expect(reconnectButton).toBeInTheDocument()
      expect(reconnectButton.closest('button')).not.toBeDisabled()
    })

    it('calls disconnect when reconnect is triggered', async () => {
      // Simulate being connected so disconnect is called first
      mockIsConnected.mockReturnValue(true)

      renderTerminal()

      const reconnectButton = screen.getByText('🔄')
      await user.click(reconnectButton.closest('button')!)

      await waitFor(() => {
        expect(mockDisconnect).toHaveBeenCalled()
      })
    })

    it('attempts to reconnect after disconnect', async () => {
      mockIsConnected.mockReturnValue(true)

      renderTerminal()

      // Clear the initial connect call
      mockConnect.mockClear()

      const reconnectButton = screen.getByText('🔄')
      await user.click(reconnectButton.closest('button')!)

      await waitFor(() => {
        // Reconnect calls connect again after disconnect
        expect(mockConnect).toHaveBeenCalled()
      })
    })
  })

  describe('Terminal Controls', () => {
    it('kill button is disabled when no processes are running', () => {
      renderTerminal()

      const killButton = screen.getByText(/🛑 KILL/).closest('button')
      expect(killButton).toBeDisabled()
    })

    it('interrupt button is disabled when no active process', () => {
      renderTerminal()

      const intButton = screen.getByText(/⚡ INT/).closest('button')
      expect(intButton).toBeDisabled()
    })

    it('pause button is disabled when no automated workflow', () => {
      renderTerminal()

      const pauseButton = screen.getByText(/⏸️ PAUSE/).closest('button')
      expect(pauseButton).toBeDisabled()
    })

    it('clear button clears terminal output', async () => {
      renderTerminal()

      const clearButton = screen.getByText('🗑️').closest('button')!
      await user.click(clearButton)

      // After clear, output should be empty (0 lines)
      expect(screen.getByText(/terminal\.window\.lines 0/)).toBeInTheDocument()
    })
  })

  describe('Terminal Input', () => {
    it('input is disabled when not connected', () => {
      renderTerminal()

      const input = document.querySelector('.terminal-input') as HTMLInputElement
      expect(input).toBeDisabled()
    })

    it('has a prompt element', () => {
      renderTerminal()

      const prompt = document.querySelector('.prompt')
      expect(prompt).not.toBeNull()
    })

    it('has a cursor element', () => {
      renderTerminal()

      const cursor = document.querySelector('.cursor')
      expect(cursor).not.toBeNull()
    })
  })

  describe('Terminal Structure', () => {
    it('has the terminal-window-standalone container', () => {
      renderTerminal()

      const container = document.querySelector('.terminal-window-standalone')
      expect(container).not.toBeNull()
    })

    it('has the terminal-main area', () => {
      renderTerminal()

      const main = document.querySelector('.terminal-main')
      expect(main).not.toBeNull()
    })

    it('has the terminal-output area', () => {
      renderTerminal()

      const output = document.querySelector('.terminal-output')
      expect(output).not.toBeNull()
    })

    it('has the status bar with connection info', () => {
      renderTerminal()

      const statusBar = document.querySelector('.terminal-status-bar')
      expect(statusBar).not.toBeNull()

      const connectionStatus = document.querySelector('.connection-status')
      expect(connectionStatus).not.toBeNull()
      // Initial state is disconnected
      expect(connectionStatus?.classList.contains('disconnected')).toBe(true)
    })
  })

  describe('Child Component Stubs', () => {
    it('renders CompletionSuggestions stub', () => {
      renderTerminal()

      expect(screen.getByTestId('completion-stub')).toBeInTheDocument()
    })

    it('renders AdvancedStepConfirmationModal stub', () => {
      renderTerminal()

      expect(screen.getByTestId('step-modal-stub')).toBeInTheDocument()
    })
  })

  describe('Button Title Attributes', () => {
    it('kill button has emergency kill title', () => {
      renderTerminal()

      const killButton = screen.getByText(/🛑 KILL/).closest('button')
      expect(killButton).toHaveAttribute('title', 'terminal.window.emergencyKillTitle')
    })

    it('interrupt button has interrupt title', () => {
      renderTerminal()

      const intButton = screen.getByText(/⚡ INT/).closest('button')
      expect(intButton).toHaveAttribute('title', 'terminal.window.interruptProcess')
    })

    it('pause button has pause automation title', () => {
      renderTerminal()

      const pauseButton = screen.getByText(/⏸️ PAUSE/).closest('button')
      expect(pauseButton).toHaveAttribute('title', 'terminal.window.pauseAutomation')
    })

    it('reconnect button has reconnect title', () => {
      renderTerminal()

      const reconnectButton = screen.getByText('🔄').closest('button')
      expect(reconnectButton).toHaveAttribute('title', 'terminal.window.reconnect')
    })

    it('clear button has clear title', () => {
      renderTerminal()

      const clearButton = screen.getByText('🗑️').closest('button')
      expect(clearButton).toHaveAttribute('title', 'terminal.window.clear')
    })

    it('close button has close window title', () => {
      renderTerminal()

      const closeButton = screen.getByText('✕').closest('button')
      expect(closeButton).toHaveAttribute('title', 'terminal.window.closeWindow')
    })
  })

  describe('Service Mock Integration', () => {
    it('uses mocked useTerminalService', () => {
      renderTerminal()

      // The component calls connect during mount
      // The mock should have been invoked
      expect(mockConnect).toHaveBeenCalled()
    })

    it('mocked connect resolves successfully', async () => {
      renderTerminal()

      await waitFor(() => {
        expect(mockConnect).toHaveBeenCalled()
      })

      // Verify the mock resolved without error
      await expect(mockConnect.mock.results[0]?.value).resolves.toBeUndefined()
    })
  })

  describe('CSS Classes', () => {
    it('applies correct classes to control buttons', () => {
      renderTerminal()

      const killButton = screen.getByText(/🛑 KILL/).closest('button')
      expect(killButton?.classList.contains('emergency-kill')).toBe(true)
      expect(killButton?.classList.contains('control-button')).toBe(true)

      const intButton = screen.getByText(/⚡ INT/).closest('button')
      expect(intButton?.classList.contains('interrupt')).toBe(true)

      const pauseButton = screen.getByText(/⏸️ PAUSE/).closest('button')
      expect(pauseButton?.classList.contains('takeover')).toBe(true)

      const closeButton = screen.getByText('✕').closest('button')
      expect(closeButton?.classList.contains('danger')).toBe(true)
    })
  })
})
