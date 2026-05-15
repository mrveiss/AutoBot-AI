import { vi, type Mock } from 'vitest'
import { createMockWebSocketEvent } from '../utils/test-utils'

// Mock WebSocket class
export class MockWebSocket {
  public url: string
  public readyState: number
  public onopen: ((event: Event) => void) | null = null
  public onclose: ((event: CloseEvent) => void) | null = null
  public onmessage: ((event: MessageEvent) => void) | null = null
  public onerror: ((event: Event) => void) | null = null
  public send: Mock = vi.fn()
  public close: Mock = vi.fn()

  // WebSocket ready states
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  // Track all instances for testing
  static instances: MockWebSocket[] = []

  constructor(url: string, protocols?: string | string[]) {
    this.url = url
    this.readyState = MockWebSocket.CONNECTING

    MockWebSocket.instances.push(this)

    // Simulate connection after a short delay
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }, 10)
  }

  // Helper methods for testing
  public simulateMessage(data: any) {
    if (this.readyState === MockWebSocket.OPEN && this.onmessage) {
      const event = new MessageEvent('message', {
        data: typeof data === 'string' ? data : JSON.stringify(data),
      })
      this.onmessage(event)
    }
  }

  public simulateError(error?: string) {
    if (this.onerror) {
      const event = new Event('error')
      ;(event as any).error = error || 'Mock WebSocket error'
      this.onerror(event)
    }
  }

  public simulateClose(code = 1000, reason = '') {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      const event = new CloseEvent('close', { code, reason })
      this.onclose(event)
    }
  }

  // Static helper methods
  static getLatestInstance(): MockWebSocket | undefined {
    return this.instances[this.instances.length - 1]
  }

  static getAllInstances(): MockWebSocket[] {
    return this.instances
  }

  static clearInstances() {
    this.instances = []
  }

  static mockImplementation() {
    // @ts-ignore
    global.WebSocket = MockWebSocket
  }

  static restoreImplementation() {
    // Restore original WebSocket if available
    if ('WebSocket' in globalThis) {
      // @ts-ignore
      delete global.WebSocket
    }
  }
}

// WebSocket message types for AutoBot
export const WebSocketMessageType = {
  CHAT_MESSAGE: 'chat_message',
  CHAT_RESPONSE: 'chat_response',
  WORKFLOW_UPDATE: 'workflow_update',
  WORKFLOW_STEP_STARTED: 'workflow_step_started',
  WORKFLOW_STEP_COMPLETED: 'workflow_step_completed',
  WORKFLOW_APPROVAL_REQUIRED: 'workflow_approval_required',
  WORKFLOW_COMPLETED: 'workflow_completed',
  WORKFLOW_FAILED: 'workflow_failed',
  TERMINAL_OUTPUT: 'terminal_output',
  TERMINAL_CONNECTED: 'terminal_connected',
  TERMINAL_DISCONNECTED: 'terminal_disconnected',
  SYSTEM_STATUS: 'system_status',
  ERROR: 'error',
} as const

// Helper to create mock WebSocket messages
export const createMockChatMessage = (content: string, sender = 'assistant') =>
  createMockWebSocketEvent(WebSocketMessageType.CHAT_MESSAGE, {
    message: { content, sender, timestamp: Date.now() },
  })

export const createMockWorkflowUpdate = (workflowId: string, status: string, step?: number) =>
  createMockWebSocketEvent(WebSocketMessageType.WORKFLOW_UPDATE, {
    workflowId,
    status,
    currentStep: step,
    timestamp: Date.now(),
  })

export const createMockTerminalOutput = (output: string, command?: string) =>
  createMockWebSocketEvent(WebSocketMessageType.TERMINAL_OUTPUT, {
    output,
    command,
    timestamp: Date.now(),
  })

export const createMockSystemStatus = (status: string, details?: any) =>
  createMockWebSocketEvent(WebSocketMessageType.SYSTEM_STATUS, {
    status,
    details,
    timestamp: Date.now(),
  })

// WebSocket test utilities
export class WebSocketTestUtil {
  private mockWs: MockWebSocket | null = null

  setup() {
    MockWebSocket.mockImplementation()
    MockWebSocket.clearInstances()
  }

  teardown() {
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    this.mockWs = null
  }

  connect(url: string): MockWebSocket {
    this.mockWs = new MockWebSocket(url)
    return this.mockWs
  }

  getConnection(): MockWebSocket | null {
    return this.mockWs || MockWebSocket.getLatestInstance() || null
  }

  simulateMessage(type: string, data: any) {
    const ws = this.getConnection()
    if (ws) {
      ws.simulateMessage(createMockWebSocketEvent(type, data))
    }
  }

  simulateChatMessage(content: string, sender = 'assistant') {
    this.simulateMessage(WebSocketMessageType.CHAT_MESSAGE, {
      message: { content, sender, timestamp: Date.now() },
    })
  }

  simulateWorkflowUpdate(workflowId: string, status: string, step?: number) {
    this.simulateMessage(WebSocketMessageType.WORKFLOW_UPDATE, {
      workflowId,
      status,
      currentStep: step,
      timestamp: Date.now(),
    })
  }

  simulateTerminalOutput(output: string, command?: string) {
    this.simulateMessage(WebSocketMessageType.TERMINAL_OUTPUT, {
      output,
      command,
      timestamp: Date.now(),
    })
  }

  simulateError(error = 'Mock WebSocket error') {
    const ws = this.getConnection()
    if (ws) {
      ws.simulateError(error)
    }
  }

  simulateClose(code = 1000, reason = '') {
    const ws = this.getConnection()
    if (ws) {
      ws.simulateClose(code, reason)
    }
  }

  expectMessageSent(expectedData?: any) {
    const ws = this.getConnection()
    expect(ws?.send).toHaveBeenCalled()

    if (expectedData) {
      expect(ws?.send).toHaveBeenCalledWith(JSON.stringify(expectedData))
    }
  }

  expectConnectionOpened() {
    const ws = this.getConnection()
    expect(ws?.readyState).toBe(MockWebSocket.OPEN)
  }

  expectConnectionClosed() {
    const ws = this.getConnection()
    expect(ws?.readyState).toBe(MockWebSocket.CLOSED)
  }
}

// Global instance for easy testing
export const webSocketTestUtil = new WebSocketTestUtil()
