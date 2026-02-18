/**
 * Test Configuration for AutoBot Frontend
 *
 * This file contains configuration specific to testing scenarios,
 * including handling backend connectivity issues and timeout scenarios.
 */

import { vi } from 'vitest'
import { NetworkConstants, ServiceURLs } from '@/constants/network'

// Test environment configuration
export const TEST_CONFIG = {
  // API Configuration
  api: {
    baseUrl: process.env.VITE_API_BASE_URL || ServiceURLs.BACKEND_LOCAL,
    timeout: 30000, // 30 seconds to match real timeout behavior
    retryAttempts: 3,
    retryDelay: 1000,
  },

  // WebSocket Configuration
  websocket: {
    url: process.env.VITE_WS_URL || ServiceURLs.WEBSOCKET_LOCAL,
    reconnectAttempts: 5,
    reconnectDelay: 2000,
  },

  // Test Timeouts
  timeouts: {
    unit: 10000,        // 10 seconds for unit tests
    integration: 30000,  // 30 seconds for integration tests
    e2e: 60000,         // 60 seconds for E2E tests
    apiCall: 35000,     // 35 seconds for API calls (slightly longer than real timeout)
  },

  // Coverage Thresholds
  coverage: {
    statements: 70,
    branches: 70,
    functions: 70,
    lines: 70,
  },

  // Test Data
  testData: {
    defaultChatId: 'test-chat-123',
    defaultUserId: 'test-user-456',
    defaultWorkflowId: 'test-workflow-789',
    sampleMessages: [
      'Hello, AutoBot!',
      'How can I help you today?',
      'This is a test message',
      'Testing the chat interface',
    ],
    sampleCommands: [
      'ls -la',
      'pwd',
      'echo "Hello World"',
      'ps aux',
      'top',
    ],
  },

  // Backend Connection Simulation
  backendStatus: {
    // Simulate different backend states for testing
    healthy: true,
    responseDelay: 0,
    errorRate: 0, // 0-100 percentage
    timeoutRate: 0, // 0-100 percentage
  },
}

// Mock API responses based on current backend status
export const createMockApiResponse = (endpoint: string, method = 'GET') => {
  const config = TEST_CONFIG.backendStatus

  // Simulate timeout (based on real application errors)
  if (Math.random() < config.timeoutRate / 100) {
    return Promise.reject(new Error('Request timeout after 30000ms'))
  }

  // Simulate general network error
  if (Math.random() < config.errorRate / 100) {
    return Promise.reject(new Error('TypeError: Failed to fetch'))
  }

  // Simulate delay
  const delay = config.responseDelay

  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(getMockResponseData(endpoint, method)),
      })
    }, delay)
  })
}

// Get mock response data based on endpoint
const getMockResponseData = (endpoint: string, method: string) => {
  const baseResponse = {
    success: true,
    timestamp: Date.now(),
  }

  // Chat endpoints
  if (endpoint.includes('/api/chat')) {
    if (method === 'POST') {
      return {
        ...baseResponse,
        data: {
          message: {
            id: `msg-${Date.now()}`,
            content: 'Mock response from AutoBot',
            sender: 'assistant',
            timestamp: Date.now(),
          },
          chatId: TEST_CONFIG.testData.defaultChatId,
        },
      }
    }

    if (endpoint.includes('/history')) {
      return {
        ...baseResponse,
        data: {
          sessions: [
            {
              chatId: TEST_CONFIG.testData.defaultChatId,
              name: 'Test Chat Session',
              messages: [],
              created: Date.now() - 3600000,
              lastActive: Date.now(),
            },
          ],
        },
      }
    }
  }

  // Settings endpoints
  if (endpoint.includes('/api/settings')) {
    return {
      ...baseResponse,
      data: {
        settings: {
          chat: {
            auto_scroll: true,
            max_messages: 100,
            message_retention_days: 30,
          },
          backend: {
            host: NetworkConstants.LOCALHOST_NAME,
            port: NetworkConstants.BACKEND_PORT,
            timeout: 30000,
          },
          ui: {
            theme: 'light',
            sidebar_collapsed: false,
          },
        },
      }
    }
  }

  // System health endpoints
  if (endpoint.includes('/api/system/health')) {
    return {
      ...baseResponse,
      data: {
        status: 'healthy',
        version: '1.0.0',
        uptime: 3600,
        services: {
          database: 'connected',
          redis: 'connected',
          llm: 'available',
        },
      },
    }
  }

  // Terminal endpoints
  // Issue #552: Backend uses /api/agent-terminal/* not /api/terminal/*
  if (endpoint.includes('/api/agent-terminal') || endpoint.includes('/api/terminal')) {
    return {
      ...baseResponse,
      data: {
        command: 'test command',
        output: 'Mock terminal output',
        exitCode: 0,
        duration: 150,
      },
    }
  }

  // Workflow endpoints
  if (endpoint.includes('/api/workflow')) {
    return {
      ...baseResponse,
      data: {
        workflows: [
          {
            id: TEST_CONFIG.testData.defaultWorkflowId,
            name: 'Test Workflow',
            status: 'running',
            steps: [
              { id: 1, name: 'Step 1', status: 'completed' },
              { id: 2, name: 'Step 2', status: 'running' },
            ],
          },
        ],
      },
    }
  }

  // Knowledge base endpoints
  if (endpoint.includes('/api/knowledge_base')) {
    return {
      ...baseResponse,
      data: {
        query: 'test query',
        results: [
          {
            id: '1',
            content: 'Mock knowledge base result',
            score: 0.95,
            metadata: { source: 'test-doc.md' },
          },
        ],
        total: 1,
      },
    }
  }

  // Default response
  return {
    ...baseResponse,
    data: {},
  }
}

// Test scenarios for different backend states
export const TEST_SCENARIOS = {
  // Normal operation
  healthy: () => {
    TEST_CONFIG.backendStatus.healthy = true
    TEST_CONFIG.backendStatus.responseDelay = 100
    TEST_CONFIG.backendStatus.errorRate = 0
    TEST_CONFIG.backendStatus.timeoutRate = 0
  },

  // Backend completely down (like in the real errors we see)
  backendDown: () => {
    TEST_CONFIG.backendStatus.healthy = false
    TEST_CONFIG.backendStatus.responseDelay = 0
    TEST_CONFIG.backendStatus.errorRate = 100
    TEST_CONFIG.backendStatus.timeoutRate = 0
  },

  // Intermittent connectivity issues
  unstableConnection: () => {
    TEST_CONFIG.backendStatus.healthy = true
    TEST_CONFIG.backendStatus.responseDelay = 2000
    TEST_CONFIG.backendStatus.errorRate = 30
    TEST_CONFIG.backendStatus.timeoutRate = 20
  },

  // Slow responses
  slowBackend: () => {
    TEST_CONFIG.backendStatus.healthy = true
    TEST_CONFIG.backendStatus.responseDelay = 5000
    TEST_CONFIG.backendStatus.errorRate = 0
    TEST_CONFIG.backendStatus.timeoutRate = 0
  },

  // Timeout-heavy (matching real application behavior)
  timeoutHeavy: () => {
    TEST_CONFIG.backendStatus.healthy = false
    TEST_CONFIG.backendStatus.responseDelay = 0
    TEST_CONFIG.backendStatus.errorRate = 0
    TEST_CONFIG.backendStatus.timeoutRate = 100
  },
}

// Initialize test environment with specific scenario
export const initializeTestScenario = (scenario: keyof typeof TEST_SCENARIOS) => {
  TEST_SCENARIOS[scenario]()

  // Setup global fetch mock based on current scenario
  global.fetch = vi.fn().mockImplementation((url: string, options: any = {}) => {
    const method = options.method || 'GET'
    return createMockApiResponse(url.toString(), method)
  }) as any
}

// Reset test configuration to defaults
export const resetTestConfig = () => {
  TEST_SCENARIOS.healthy()
}

// Utility to simulate real backend errors we see in the logs
export const simulateRealBackendErrors = () => {
  const wsUrl = TEST_CONFIG.websocket.url
  const errors = [
    'Request timeout after 30000ms',
    'TypeError: Failed to fetch',
    `WebSocket connection to '${wsUrl}' failed`,
    'Error in connection establishment: net::ERR_CONNECTION_REFUSED',
  ]

  return errors[Math.floor(Math.random() * errors.length)]
}

// Helper to create consistent test IDs
export const createTestId = (component: string, element: string) => {
  return `${component.toLowerCase()}-${element.toLowerCase()}`
}

// Common test assertions for API calls
export const expectApiCall = {
  toTimeout: (promise: Promise<any>) => {
    return expect(promise).rejects.toThrow(/timeout|30000ms/)
  },

  toFail: (promise: Promise<any>) => {
    return expect(promise).rejects.toThrow(/Failed to fetch|TypeError/)
  },

  toSucceed: (promise: Promise<any>) => {
    return expect(promise).resolves.toEqual(
      expect.objectContaining({
        success: true,
        data: expect.any(Object),
      })
    )
  },
}

// WebSocket test utilities
export const mockWebSocketBehavior = {
  connectionRefused: () => {
    global.WebSocket = vi.fn().mockImplementation(() => {
      throw new Error('Error in connection establishment: net::ERR_CONNECTION_REFUSED')
    }) as any
  },

  connectionTimeout: () => {
    global.WebSocket = vi.fn().mockImplementation((url) => {
      const ws = {
        url,
        readyState: WebSocket.CONNECTING,
        send: vi.fn(),
        close: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        onerror: null as any,
      }

      // Simulate connection timeout after 30 seconds
      setTimeout(() => {
        if (ws.onerror) {
          ws.onerror(new Event('error'))
        }
      }, 30000)

      return ws
    }) as any
  },

  normalConnection: () => {
    global.WebSocket = vi.fn().mockImplementation((url) => ({
      url,
      readyState: WebSocket.OPEN,
      send: vi.fn(),
      close: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
    })) as any
  },
}

// Export default configuration
export default TEST_CONFIG
