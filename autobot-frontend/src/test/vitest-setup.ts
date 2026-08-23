// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import '@testing-library/jest-dom'
import { vi, afterAll, afterEach } from 'vitest'
import { enableAutoUnmount } from '@vue/test-utils'

// #14842/#14613: destroy every mounted component tree after the test that made
// it. The `beforeEach` below resets `document.body.innerHTML`, which DETACHES a
// mounted tree's DOM but never unmounts the app — its component instances,
// watchers and effects stay live for the rest of the file. A file that mounts
// 30 times therefore ran its last test with 29 live trees still reacting to
// every shared ref it touched, and the per-test cost grew as the file
// progressed. That is why the failures land on a different test each run and
// why a file passes alone but times out inside a larger, more loaded run.
//
// This generalises the per-file teardown that `OrgChart.canvasFilters.test.ts`
// already carried, where the same accumulation was measured at ~3.4s on a quiet
// runner against the 10s per-test ceiling on a loaded one. Unmounting is the
// fix rather than a longer timeout: a longer timeout keeps the accumulation and
// only raises the load needed to trip it.
//
// Safe against a test that unmounts its own wrapper — Vue's `app.unmount()` is
// idempotent — and against a test that depends on a previous test's DOM,
// because the `beforeEach` below already made that impossible.
enableAutoUnmount(afterEach)

// Prevent cross-file pollution: some test files call vi.stubGlobal() (e.g. window,
// navigator, EventSource) at module scope without restoring. Under parallel file
// execution these leak into later files' worker context, causing flaky failures
// (async DOM updates/emits break). Restore all stubbed globals after each file.
afterAll(() => {
  vi.unstubAllGlobals()
})

// Wrap global fetch to resolve relative URLs against document origin (jsdom 29+ compat)
const originalFetch = global.fetch
global.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
  if (typeof input === 'string' && input.startsWith('/')) {
    const base = globalThis.location?.origin || 'http://localhost'
    input = `${base}${input}`
  }
  return originalFetch(input, init)
}) as typeof fetch

// Mock IntersectionObserver (not available in jsdom 29+)
class MockIntersectionObserver {
  readonly root: Element | null = null
  readonly rootMargin: string = ''
  readonly thresholds: ReadonlyArray<number> = []
  constructor(
    private callback: IntersectionObserverCallback,
    _options?: IntersectionObserverInit,
  ) {}
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
  takeRecords = vi.fn().mockReturnValue([])
}
global.IntersectionObserver = MockIntersectionObserver as unknown as typeof IntersectionObserver

// Mock ResizeObserver (not available in jsdom 29+)
class MockResizeObserver {
  constructor(private callback: ResizeObserverCallback) {}
  observe = vi.fn()
  unobserve = vi.fn()
  disconnect = vi.fn()
}
global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver

// Mock window.matchMedia (not available in jsdom).
// #9693: MUST be a plain function, not vi.fn() — `mockReset: true` in
// vitest.config.ts wipes vi.fn() implementations after the first test,
// making matchMedia() return undefined for every subsequent mount.
const createMatchMediaStub = (query: string): MediaQueryList =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }) as unknown as MediaQueryList
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: createMatchMediaStub,
})

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  public readyState = MockWebSocket.CONNECTING
  public url: string
  public onopen: ((event: Event) => void) | null = null
  public onclose: ((event: CloseEvent) => void) | null = null
  public onmessage: ((event: MessageEvent) => void) | null = null
  public onerror: ((event: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }, 10)
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
    if (this.onclose) {
      this.onclose(new CloseEvent('close'))
    }
  })

  // Simulate message reception
  simulateMessage(data: unknown) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
    }
  }

  // Simulate error
  simulateError(_error: string) {
    if (this.onerror) {
      this.onerror(new Event('error'))
    }
  }
}

// Replace global WebSocket
global.WebSocket = MockWebSocket as unknown as typeof WebSocket

// Global test setup
beforeEach(() => {
  // Clear all mocks before each test
  vi.clearAllMocks()

  // Reset DOM
  document.body.innerHTML = ''

  // Reset location
  Object.defineProperty(window, 'location', {
    value: {
      href: 'http://localhost:3000',
      origin: 'http://localhost:3000',
      protocol: 'http:',
      hostname: 'localhost',
      port: '3000',
      pathname: '/',
      search: '',
      hash: '',
      reload: vi.fn(),
      assign: vi.fn(),
      replace: vi.fn()
    },
    writable: true
  })
})
