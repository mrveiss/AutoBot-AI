// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * The shared TTS stream socket authenticates with the bearer subprotocol
 * (#17004). The backend route calls authenticate_websocket and has no cookie
 * fallback, so a socket opened without it is closed with 4001.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

const mockSubprotocols = vi.fn<() => string[] | null>()

vi.mock('@/utils/buildAuthenticatedWsUrl', () => ({
  buildAuthenticatedWsSubprotocols: () => mockSubprotocols(),
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ showToast: vi.fn(), toasts: { value: [] }, removeToast: vi.fn(), clearAllToasts: vi.fn() }),
}))
vi.mock('@/composables/useVoiceProfiles', () => ({
  useVoiceProfiles: () => ({ voices: ref([{ id: 'v1' }]), fetchVoices: vi.fn(), effectiveVoiceId: ref('') }),
}))
vi.mock('@/composables/usePreferences', () => ({
  usePreferences: () => ({ language: ref('en') }),
}))
vi.mock('@/utils/fetchWithAuth', () => ({ fetchWithAuth: vi.fn() }))
vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
  getBackendWsUrl: () => 'ws://test',
}))
vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

const opened: Array<{ url: string; protocols: unknown }> = []

class RecordingWebSocket {
  static OPEN = 1
  readyState = 0
  onopen: ((e?: unknown) => void) | null = null
  onerror: ((e?: unknown) => void) | null = null
  onclose: ((e?: unknown) => void) | null = null
  onmessage: ((e?: unknown) => void) | null = null
  constructor(url: string, protocols?: unknown) {
    opened.push({ url, protocols })
  }
  send() {}
  close() {}
}

describe('useVoiceOutput — TTS stream socket auth (#17004)', () => {
  let originalWebSocket: unknown

  beforeEach(() => {
    vi.resetModules()
    opened.length = 0
    originalWebSocket = (globalThis as Record<string, unknown>).WebSocket
    ;(globalThis as Record<string, unknown>).WebSocket = RecordingWebSocket
  })

  afterEach(() => {
    ;(globalThis as Record<string, unknown>).WebSocket = originalWebSocket
  })

  it('opens /api/voice/stream with the bearer subprotocol and no URL token', async () => {
    mockSubprotocols.mockReturnValue(['bearer', 'tok-123'])
    const { useVoiceOutput } = await import('../useVoiceOutput')

    useVoiceOutput().subscribeVoiceMessages(() => {})

    expect(opened).toEqual([{ url: 'ws://test/api/voice/stream', protocols: ['bearer', 'tok-123'] }])
  })

  it('passes no protocol list, never the string "null", when no token exists yet', async () => {
    mockSubprotocols.mockReturnValue(null)
    const { useVoiceOutput } = await import('../useVoiceOutput')

    useVoiceOutput().subscribeVoiceMessages(() => {})

    expect(opened).toEqual([{ url: 'ws://test/api/voice/stream', protocols: undefined }])
  })
})
