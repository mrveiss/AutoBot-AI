import { render, type RenderOptions } from '@testing-library/vue'
import { createTestingPinia } from '@pinia/testing'
import { createRouter, createMemoryHistory } from 'vue-router'
import { vi, type Mock } from 'vitest'
import type { Component } from 'vue'

// Common test routes for components that use router
const testRoutes = [
  { path: '/', name: 'home', component: { template: '<div>Home</div>' } },
  { path: '/about', name: 'about', component: { template: '<div>About</div>' } },
  { path: '/settings', name: 'settings', component: { template: '<div>Settings</div>' } },
  { path: '/terminal/:sessionId?', name: 'terminal', component: { template: '<div>Terminal</div>' } },
]

// Create test router
export const createTestRouter = (routes = testRoutes, initialEntries = ['/']) => {
  const router = createRouter({
    // Issue #156 Fix: createMemoryHistory() takes no arguments, use router.push() for initial route
    history: createMemoryHistory(),
    routes,
  })

  // For tests that need specific routes, push to the route first
  if (initialEntries.length > 0) {
    router.push(initialEntries[0])
  }

  return router
}

// Enhanced render function with common setup
// Issue #156 Fix: RenderOptions<C> requires 1 type argument
export interface CustomRenderOptions extends Omit<RenderOptions<any>, 'global'> {
  router?: boolean
  pinia?: boolean
  global?: RenderOptions<any>['global']
}

export const renderComponent = (
  component: Component,
  options: CustomRenderOptions = {}
) => {
  const { router = false, pinia = false, global = {}, ...renderOptions } = options

  // Issue #156 Fix: RenderOptions<C> requires 1 type argument
  const globalConfig: RenderOptions<any>['global'] = {
    ...global,
    plugins: [
      ...(global.plugins || []),
      ...(router ? [createTestRouter(undefined, ['/terminal/test-session'])] : []),
      ...(pinia ? [createTestingPinia({ createSpy: vi.fn })] : []),
    ],
  }

  return render(component, {
    ...renderOptions,
    global: globalConfig,
  })
}

// Helper to wait for Vue's nextTick and DOM updates
export const waitForUpdate = async () => {
  await new Promise(resolve => setTimeout(resolve, 0))
}

// Mock factory for API responses
export const createMockApiResponse = <T>(data: T, success = true) => ({
  success,
  data,
  error: success ? null : 'Mock error',
  timestamp: Date.now(),
})

// Mock factory for WebSocket events
export const createMockWebSocketEvent = (type: string, data: any) => ({
  type,
  data: JSON.stringify(data),
  timestamp: Date.now(),
})

// Mock factory for chat messages
export const createMockChatMessage = (overrides = {}) => ({
  id: `msg_${Math.random().toString(36).substr(2, 9)}`,
  content: 'Test message content',
  sender: 'user',
  timestamp: Date.now(),
  type: 'text',
  ...overrides,
})

// Mock factory for chat sessions
export const createMockChatSession = (overrides = {}) => ({
  chatId: `chat_${Math.random().toString(36).substr(2, 9)}`,
  name: 'Test Chat Session',
  messages: [],
  created: Date.now(),
  lastActive: Date.now(),
  ...overrides,
})

// Mock factory for workflow data
export const createMockWorkflow = (overrides = {}) => ({
  id: `workflow_${Math.random().toString(36).substr(2, 9)}`,
  name: 'Test Workflow',
  status: 'pending',
  steps: [],
  created: Date.now(),
  ...overrides,
})

// Mock factory for terminal session data
export const createMockTerminalSession = (overrides = {}) => ({
  sessionId: `session_${Math.random().toString(36).substr(2, 9)}`,
  title: 'Test Terminal Session',
  connected: true,
  hasRunningProcesses: false,
  hasActiveProcess: false,
  hasAutomatedWorkflow: false,
  automationPaused: false,
  ...overrides,
})

// Mock factory for settings data
export const createMockSettings = (overrides = {}) => ({
  chat: {
    auto_scroll: true,
    max_messages: 100,
    message_retention_days: 30,
  },
  backend: {
    host: 'localhost',
    port: 8001,
    timeout: 30000,
  },
  ui: {
    theme: 'light',
    sidebar_collapsed: false,
  },
  ...overrides,
})

// Helper to create mock functions with return values
// Issue #156 Fix: Vitest Mock<T> requires 0-1 type arguments, not 2
export const createMockFn = <T extends (...args: any[]) => any>(
  returnValue?: ReturnType<T>
): Mock<T> => {
  const mockFn = vi.fn() as Mock<T>
  if (returnValue !== undefined) {
    mockFn.mockReturnValue(returnValue)
  }
  return mockFn
}

// Helper to create mock functions that resolve with values
// Issue #156 Fix: Vitest Mock<T> requires 0-1 type arguments, not 2
export const createMockAsyncFn = <T extends (...args: any[]) => Promise<any>>(
  resolveValue?: Awaited<ReturnType<T>>
): Mock<T> => {
  const mockFn = vi.fn() as Mock<T>
  if (resolveValue !== undefined) {
    mockFn.mockResolvedValue(resolveValue)
  }
  return mockFn
}

// Helper to simulate user events with delays
export const simulateTyping = async (element: HTMLElement, text: string, delay = 50) => {
  for (const char of text) {
    element.dispatchEvent(new KeyboardEvent('keydown', { key: char }))
    element.dispatchEvent(new KeyboardEvent('keyup', { key: char }))
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
      element.value += char
      element.dispatchEvent(new Event('input', { bubbles: true }))
    }
    await new Promise(resolve => setTimeout(resolve, delay))
  }
}

// Helper to wait for element to appear
export const waitForElement = async (
  selector: string,
  container: HTMLElement = document.body,
  timeout = 5000
): Promise<HTMLElement> => {
  return new Promise((resolve, reject) => {
    const startTime = Date.now()

    const checkElement = () => {
      const element = container.querySelector(selector) as HTMLElement
      if (element) {
        resolve(element)
        return
      }

      if (Date.now() - startTime > timeout) {
        reject(new Error(`Element with selector "${selector}" not found within ${timeout}ms`))
        return
      }

      setTimeout(checkElement, 100)
    }

    checkElement()
  })
}

// Helper to wait for condition to be true
export const waitForCondition = async (
  condition: () => boolean,
  timeout = 5000,
  interval = 100
): Promise<void> => {
  return new Promise((resolve, reject) => {
    const startTime = Date.now()

    const checkCondition = () => {
      if (condition()) {
        resolve()
        return
      }

      if (Date.now() - startTime > timeout) {
        reject(new Error(`Condition not met within ${timeout}ms`))
        return
      }

      setTimeout(checkCondition, interval)
    }

    checkCondition()
  })
}
