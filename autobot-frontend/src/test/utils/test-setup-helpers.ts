import { vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import type { Router } from 'vue-router'
// Issue #172: Import from consolidated network.ts (TypeScript + .env support)
import { NetworkConstants, ServiceURLs } from '@/constants/network'

/**
 * Setup helpers for consistent test environment configuration
 */

// Mock environment variables
export const setupTestEnv = () => {
  process.env.NODE_ENV = 'test'
  process.env.VITE_API_BASE_URL = ServiceURLs.BACKEND_LOCAL
  process.env.VITE_WS_URL = ServiceURLs.WEBSOCKET_LOCAL
}

// Mock window properties commonly used in components
export const setupWindowMocks = () => {
  // Mock window.location
  // Issue #156 Fix: Type assertion for window.location mock
  delete (window as any).location
  ;(window as any).location = {
    ...window.location,
    href: 'http://localhost:3000/',
    origin: 'http://localhost:3000',
    reload: vi.fn(),
    assign: vi.fn(),
  }

  // Mock window.open
  window.open = vi.fn()

  // Mock window.alert, confirm, prompt
  window.alert = vi.fn()
  window.confirm = vi.fn(() => true)
  window.prompt = vi.fn(() => 'test')

  // Mock clipboard API
  Object.assign(navigator, {
    clipboard: {
      writeText: vi.fn(() => Promise.resolve()),
      readText: vi.fn(() => Promise.resolve('test')),
    },
  })

  // Mock geolocation
  Object.assign(navigator, {
    geolocation: {
      getCurrentPosition: vi.fn((success) => {
        success({
          coords: {
            latitude: 40.7128,
            longitude: -74.0060,
            accuracy: 100,
          },
        })
      }),
      watchPosition: vi.fn(),
      clearWatch: vi.fn(),
    },
  })

  // Mock notification API
  // Issue #156 Fix: Type assertions for Notification mock
  global.Notification = vi.fn() as any
  ;(global.Notification as any).permission = 'granted'
  ;(global.Notification as any).requestPermission = vi.fn(() => Promise.resolve('granted'))
}

// Setup Pinia store for testing
export const setupPiniaStore = () => {
  const pinia = createPinia()
  setActivePinia(pinia)
  return pinia
}

// Setup Vue Router for testing
export const setupTestRouter = (routes: any[] = []) => {
  const defaultRoutes = [
    { path: '/', name: 'home', component: { template: '<div>Home</div>' } },
    { path: '/chat', name: 'chat', component: { template: '<div>Chat</div>' } },
    { path: '/terminal', name: 'terminal', component: { template: '<div>Terminal</div>' } },
    { path: '/settings', name: 'settings', component: { template: '<div>Settings</div>' } },
    { path: '/about', name: 'about', component: { template: '<div>About</div>' } },
  ]

  const router = createRouter({
    history: createWebHistory(),
    routes: routes.length > 0 ? routes : defaultRoutes,
  })

  return router
}

// Mock fetch API with custom responses
export const setupFetchMock = (responses: Record<string, any> = {}) => {
  // Issue #156 Fix: Type url parameter as string | URL
  global.fetch = vi.fn((url: string | URL, options?: any) => {
    const urlString = typeof url === 'string' ? url : url.toString()
    const method = options?.method || 'GET'
    const key = `${method} ${urlString}`

    const defaultResponse = {
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: () => Promise.resolve({ success: true, data: {} }),
      text: () => Promise.resolve(''),
      blob: () => Promise.resolve(new Blob()),
    }

    if (responses[key]) {
      return Promise.resolve({
        ...defaultResponse,
        json: () => Promise.resolve(responses[key]),
      })
    }

    // Default timeout simulation for backend connectivity issues
    // Use NetworkConstants to check for backend host instead of hardcoded value
    if (urlString.includes(`${NetworkConstants.LOCALHOST_NAME}:${NetworkConstants.BACKEND_PORT}`)) {
      return Promise.reject(new Error('Request timeout after 30000ms'))
    }

    return Promise.resolve(defaultResponse)
  }) as any
}

// Setup WebSocket mocks
export const setupWebSocketMocks = () => {
  global.WebSocket = vi.fn().mockImplementation((url) => ({
    url,
    readyState: WebSocket.OPEN,
    send: vi.fn(),
    close: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onopen: null,
    onclose: null,
    onmessage: null,
    onerror: null,
  })) as any

  // WebSocket constants
  // Issue #156 Fix: Type assertions for read-only WebSocket constants
  ;(global.WebSocket as any).CONNECTING = 0
  ;(global.WebSocket as any).OPEN = 1
  ;(global.WebSocket as any).CLOSING = 2
  ;(global.WebSocket as any).CLOSED = 3
}

// Setup console mocks to reduce test noise
export const setupConsoleMocks = () => {
  const originalConsole = { ...console }

  global.console = {
    ...console,
    log: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
  }

  return originalConsole
}

// Setup timer mocks
export const setupTimerMocks = () => {
  vi.useFakeTimers()

  return {
    runAllTimers: () => vi.runAllTimers(),
    runOnlyPendingTimers: () => vi.runOnlyPendingTimers(),
    advanceTimersByTime: (ms: number) => vi.advanceTimersByTime(ms),
    clearAllTimers: () => vi.clearAllTimers(),
    useRealTimers: () => vi.useRealTimers(),
  }
}

// Mock IntersectionObserver for components that use it
export const setupIntersectionObserverMock = () => {
  global.IntersectionObserver = vi.fn().mockImplementation((callback) => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
    root: null,
    rootMargin: '',
    thresholds: [],
  }))
}

// Mock ResizeObserver for responsive components
export const setupResizeObserverMock = () => {
  global.ResizeObserver = vi.fn().mockImplementation((callback) => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  }))
}

// Setup media query mocks
export const setupMediaQueryMocks = () => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(), // deprecated
      removeListener: vi.fn(), // deprecated
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

// Mock File API for file upload components
export const setupFileAPIMocks = () => {
  global.File = vi.fn().mockImplementation((parts, filename, properties) => ({
    name: filename,
    size: parts.join('').length,
    type: properties?.type || 'text/plain',
    lastModified: Date.now(),
    arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
    slice: vi.fn(),
    stream: vi.fn(),
    text: () => Promise.resolve(parts.join('')),
  })) as any

  global.FileReader = vi.fn().mockImplementation(() => ({
    readAsDataURL: vi.fn(),
    readAsText: vi.fn(),
    readAsArrayBuffer: vi.fn(),
    abort: vi.fn(),
    result: null,
    error: null,
    onload: null,
    onerror: null,
    onabort: null,
    onloadstart: null,
    onloadend: null,
    onprogress: null,
    EMPTY: 0,
    LOADING: 1,
    DONE: 2,
    readyState: 0,
  })) as any
}

// Comprehensive test environment setup
export const setupTestEnvironment = (options: {
  includeRouter?: boolean
  includePinia?: boolean
  mockFetch?: boolean
  mockWebSocket?: boolean
  mockTimers?: boolean
  fetchResponses?: Record<string, any>
} = {}) => {
  const {
    includeRouter = true,
    includePinia = true,
    mockFetch = true,
    mockWebSocket = true,
    mockTimers = false,
    fetchResponses = {},
  } = options

  // Setup base environment
  setupTestEnv()
  setupWindowMocks()
  setupConsoleMocks()
  setupIntersectionObserverMock()
  setupResizeObserverMock()
  setupMediaQueryMocks()
  setupFileAPIMocks()

  const setup: {
    router?: Router
    pinia?: any
    timers?: any
  } = {}

  // Optional setups
  if (includeRouter) {
    setup.router = setupTestRouter()
  }

  if (includePinia) {
    setup.pinia = setupPiniaStore()
  }

  if (mockFetch) {
    setupFetchMock(fetchResponses)
  }

  if (mockWebSocket) {
    setupWebSocketMocks()
  }

  if (mockTimers) {
    setup.timers = setupTimerMocks()
  }

  return setup
}

// Cleanup function for tests
export const cleanupTestEnvironment = () => {
  vi.clearAllMocks()
  vi.clearAllTimers()
  vi.restoreAllMocks()

  // Clear localStorage and sessionStorage
  if (typeof Storage !== 'undefined') {
    localStorage.clear()
    sessionStorage.clear()
  }

  // Reset DOM
  if (typeof document !== 'undefined') {
    document.body.innerHTML = ''
  }
}

// Test data generators for common scenarios
export const generateTestData = {
  user: (overrides = {}) => ({
    id: 'test-user-123',
    name: 'Test User',
    email: 'test@example.com',
    role: 'user',
    createdAt: new Date().toISOString(),
    ...overrides,
  }),

  apiResponse: (data: any, success = true) => ({
    success,
    data,
    message: success ? 'Success' : 'Error occurred',
    timestamp: Date.now(),
    error: success ? null : 'Test error',
  }),

  chatMessage: (overrides = {}) => ({
    id: `msg-${Date.now()}`,
    content: 'Test message',
    sender: 'user',
    timestamp: Date.now(),
    type: 'text',
    ...overrides,
  }),

  workflowStep: (overrides = {}) => ({
    id: `step-${Date.now()}`,
    name: 'Test Step',
    status: 'pending',
    description: 'Test step description',
    estimatedDuration: 5000,
    ...overrides,
  }),

  terminalOutput: (overrides = {}) => ({
    command: 'test command',
    output: 'test output',
    exitCode: 0,
    timestamp: Date.now(),
    ...overrides,
  }),
}
