// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Unit Tests for useRealtimeVoice composable (#7345)
 *
 * Covers:
 * - Mode transition (connect / disconnect)
 * - SDP exchange via mocked fetch (POST /api/voice/realtime/session)
 * - Tool registration message shape (session.update)
 * - Tool-call routing (response.function_call_arguments.done → POST tools/call)
 * - Disconnect cleanup (peer closed, tracks stopped, pending calls aborted)
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { nextTick } from 'vue'

// ─── Dependency mocks ────────────────────────────────────

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => 'http://localhost:8001/api',
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ debug: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

const mockFetchWithAuth = vi.fn()
vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: (...args: unknown[]) => mockFetchWithAuth(...args),
}))

// ─── Browser API mocks ───────────────────────────────────

const sentMessages: string[] = []

// Data-channel mock — callbacks stored as plain props so triggerX helpers work
const mockDC = {
  readyState: 'open' as RTCDataChannelState,
  onopen: null as (() => void) | null,
  onmessage: null as ((ev: { data: string }) => void) | null,
  onclose: null as (() => void) | null,
  send: vi.fn((msg: string) => sentMessages.push(msg)),
  close: vi.fn(),
}

const mockTrack = { stop: vi.fn() }
const mockStream = { getTracks: () => [mockTrack] }

// PeerConnection mock — stored separately so we can spy per-test
const mockPC = {
  addTrack: vi.fn(),
  createDataChannel: vi.fn().mockReturnValue(mockDC),
  createOffer: vi.fn().mockResolvedValue({ sdp: 'offer-sdp', type: 'offer' as RTCSdpType }),
  setLocalDescription: vi.fn().mockResolvedValue(undefined),
  setRemoteDescription: vi.fn().mockResolvedValue(undefined),
  close: vi.fn(),
  connectionState: 'connected' as RTCPeerConnectionState,
  onconnectionstatechange: null as (() => void) | null,
}

// RTCPeerConnection must be a class (arrow fn can't be a constructor)
class RTCPeerConnectionMock {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  constructor() { return mockPC as any }
}
vi.stubGlobal('RTCPeerConnection', RTCPeerConnectionMock)
vi.stubGlobal('RTCSessionDescription', function RTCSessionDescriptionMock(
  init: RTCSessionDescriptionInit,
) { return init })
vi.stubGlobal('navigator', {
  mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(mockStream) },
})
vi.stubGlobal('window', { isSecureContext: true })

// ─── Helpers ─────────────────────────────────────────────

function makeJsonResponse(body: unknown, ok = true): Response {
  return { ok, status: ok ? 200 : 500, json: async () => body } as unknown as Response
}

function setFetchMock(overrides: Record<string, unknown> = {}) {
  mockFetchWithAuth.mockImplementation(async (url: string) => {
    if (url.includes('/voice/realtime/session')) {
      return makeJsonResponse(overrides['session'] ?? { sdp: 'answer-sdp' })
    }
    if (url.includes('/voice/realtime/tools/call')) {
      return overrides['toolsCall']
        ? makeJsonResponse(overrides['toolsCall'])
        : makeJsonResponse({}, false)
    }
    if (url.includes('/voice/realtime/tools')) {
      return makeJsonResponse({ tools: overrides['tools'] ?? [] })
    }
    return makeJsonResponse({})
  })
}

// ─── Composable import ───────────────────────────────────

import { useRealtimeVoice } from '../useRealtimeVoice'

// ─── Tests ───────────────────────────────────────────────

describe('useRealtimeVoice', () => {
  let rtv: ReturnType<typeof useRealtimeVoice>

  beforeEach(() => {
    sentMessages.length = 0
    mockDC.onopen = null
    mockDC.onmessage = null
    mockDC.send.mockClear()
    mockDC.close.mockClear()
    mockPC.addTrack.mockClear()
    mockPC.createDataChannel.mockClear().mockReturnValue(mockDC)
    mockPC.createOffer.mockClear().mockResolvedValue({ sdp: 'offer-sdp', type: 'offer' as RTCSdpType })
    mockPC.setLocalDescription.mockClear().mockResolvedValue(undefined)
    mockPC.setRemoteDescription.mockClear().mockResolvedValue(undefined)
    mockPC.close.mockClear()
    mockTrack.stop.mockClear()
    ;(navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>)
      .mockClear()
      .mockResolvedValue(mockStream)
    setFetchMock({ session: { sdp: 'answer-sdp' }, tools: [] })
    rtv = useRealtimeVoice()
  })

  afterEach(() => {
    rtv.disconnect()
  })

  // ── Connection lifecycle ─────────────────────────────

  it('starts disconnected', () => {
    expect(rtv.connectionState.value).toBe('disconnected')
  })

  it('performs full SDP exchange on connect()', async () => {
    const connectPromise = rtv.connect()
    expect(rtv.connectionState.value).toBe('connecting')
    await connectPromise

    expect(mockPC.createOffer).toHaveBeenCalledOnce()
    expect(mockPC.setLocalDescription).toHaveBeenCalledWith(
      expect.objectContaining({ sdp: 'offer-sdp' }),
    )
    expect(mockFetchWithAuth).toHaveBeenCalledWith(
      expect.stringContaining('/voice/realtime/session'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mockPC.setRemoteDescription).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'answer', sdp: 'answer-sdp' }),
    )
  })

  it('sets failed state when SDP proxy returns non-200', async () => {
    setFetchMock({ session: undefined })
    mockFetchWithAuth.mockImplementation(async () => makeJsonResponse({}, false))
    await rtv.connect()
    expect(rtv.connectionState.value).toBe('failed')
    expect(rtv.errorMessage.value).toMatch(/SDP proxy/i)
  })

  it('closes peer and stops mic tracks on disconnect()', async () => {
    await rtv.connect()
    rtv.disconnect()
    expect(mockPC.close).toHaveBeenCalledOnce()
    expect(mockTrack.stop).toHaveBeenCalledOnce()
    expect(rtv.connectionState.value).toBe('disconnected')
  })

  it('does not start a second connection when already connected', async () => {
    await rtv.connect()
    const callsBefore = mockPC.createOffer.mock.calls.length
    await rtv.connect()
    expect(mockPC.createOffer.mock.calls.length).toBe(callsBefore)
  })

  // ── Tool registration ────────────────────────────────

  it('sends session.update with correct tool shape when data channel opens', async () => {
    const tools = [
      { name: 'search', description: 'Search KB', parameters: { type: 'object', properties: {} } },
    ]
    setFetchMock({ session: { sdp: 'answer-sdp' }, tools })

    await rtv.connect()

    // Simulate browser firing the datachannel open event
    mockDC.onopen?.()
    await nextTick()
    await new Promise((r) => setTimeout(r, 20))

    const raw = sentMessages.find((m) => {
      try { return (JSON.parse(m) as { type: string }).type === 'session.update' } catch { return false }
    })
    expect(raw).toBeDefined()
    const msg = JSON.parse(raw!) as { session: { tools: Array<{ name: string; type: string }> } }
    expect(msg.session.tools).toHaveLength(1)
    expect(msg.session.tools[0]).toMatchObject({ type: 'function', name: 'search', description: 'Search KB' })
  })

  it('skips session.update when tool list is empty', async () => {
    setFetchMock({ session: { sdp: 'answer-sdp' }, tools: [] })
    await rtv.connect()
    mockDC.onopen?.()
    await nextTick()
    await new Promise((r) => setTimeout(r, 20))

    const raw = sentMessages.find((m) => {
      try { return (JSON.parse(m) as { type: string }).type === 'session.update' } catch { return false }
    })
    expect(raw).toBeUndefined()
  })

  // ── Tool-call routing ────────────────────────────────

  it('dispatches tool call to backend and returns result via data channel', async () => {
    setFetchMock({ session: { sdp: 'answer-sdp' }, tools: [], toolsCall: { answer: 42 } })
    await rtv.connect()

    mockDC.onmessage?.({ data: JSON.stringify({
      type: 'response.function_call_arguments.done',
      call_id: 'call_abc',
      name: 'search',
      arguments: '{"query":"hello"}',
    }) })
    await nextTick()
    await new Promise((r) => setTimeout(r, 20))

    expect(mockFetchWithAuth).toHaveBeenCalledWith(
      expect.stringContaining('/voice/realtime/tools/call'),
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('call_abc'),
      }),
    )
    const raw = sentMessages.find((m) => {
      try { return (JSON.parse(m) as { type: string }).type === 'conversation.item.create' } catch { return false }
    })
    expect(raw).toBeDefined()
    const out = JSON.parse(raw!) as { item: { type: string; call_id: string; output: string } }
    expect(out.item).toMatchObject({ type: 'function_call_output', call_id: 'call_abc' })
    expect(JSON.parse(out.item.output)).toEqual({ answer: 42 })
  })

  it('sends error output when tool call backend returns non-200', async () => {
    setFetchMock({ session: { sdp: 'answer-sdp' }, tools: [] })
    // toolsCall not set → defaults to non-200 in setFetchMock
    await rtv.connect()

    mockDC.onmessage?.({ data: JSON.stringify({
      type: 'response.function_call_arguments.done',
      call_id: 'call_err',
      name: 'search',
      arguments: '{}',
    }) })
    await nextTick()
    await new Promise((r) => setTimeout(r, 20))

    const raw = sentMessages.find((m) => {
      try {
        const p = JSON.parse(m) as { item?: { output?: string } }
        return typeof p.item?.output === 'string' && p.item.output.includes('error')
      } catch { return false }
    })
    expect(raw).toBeDefined()
  })

  it('ignores non-JSON and unknown event types without throwing', async () => {
    await rtv.connect()
    expect(() => {
      mockDC.onmessage?.({ data: 'not-json' })
      mockDC.onmessage?.({ data: JSON.stringify({ type: 'session.created' }) })
    }).not.toThrow()
  })

  // ── Disconnect cleanup ───────────────────────────────

  it('aborts in-flight tool calls when disconnected', async () => {
    let capturedSignal: AbortSignal | undefined
    mockFetchWithAuth.mockImplementation(async (url: string, opts: { signal?: AbortSignal }) => {
      if (url.includes('/voice/realtime/tools/call')) {
        capturedSignal = opts.signal
        return new Promise<Response>((_, reject) => {
          opts.signal?.addEventListener('abort', () =>
            reject(new DOMException('Aborted', 'AbortError')),
          )
        })
      }
      if (url.includes('/voice/realtime/session')) return makeJsonResponse({ sdp: 'answer-sdp' })
      return makeJsonResponse({ tools: [] })
    })

    await rtv.connect()

    mockDC.onmessage?.({ data: JSON.stringify({
      type: 'response.function_call_arguments.done',
      call_id: 'call_slow',
      name: 'slow_fn',
      arguments: '{}',
    }) })
    await nextTick()

    rtv.disconnect()
    expect(capturedSignal?.aborted).toBe(true)
  })
})
