// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #12460: the TTS worker sustains well below real time on a loaded host (19 of
// 19 measured syntheses at 0.09x-0.83x). Gapless scheduling assumes chunks
// arrive at least as fast as they play, so every late chunk was re-anchored to
// ctx.currentTime and the listener heard ~250ms of speech per gap — the
// reported stutter.
//
// These tests drive the real WebSocket path (tts_start / tts_audio / tts_end)
// and assert the adaptive pre-roll: nothing is held until a production rate has
// been measured, a below-real-time rate buys a lead-in before playback starts,
// the tail is always flushed, and a barge-in drops what is held.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: vi.fn(),
    toasts: { value: [] },
    removeToast: vi.fn(),
    clearAllToasts: vi.fn(),
  }),
}))

vi.mock('@/composables/useVoiceProfiles', () => ({
  useVoiceProfiles: () => ({
    voices: ref([{ id: 'v1' }]),
    fetchVoices: vi.fn(),
    effectiveVoiceId: ref('v1'),
  }),
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

// ── Controllable fakes ─────────────────────────────────────────────────────
let clockMs = 1_700_000_000_000
let ctxTime = 0
let chunkDurationSec = 0.25
let scheduledStarts = 0

class FakeBufferSource {
  buffer: unknown = null
  onended: (() => void) | null = null
  connect() {}
  start() {
    scheduledStarts++
  }
  stop() {}
}

class FakeAudioContext {
  destination = {}
  state = 'running'
  get currentTime() {
    return ctxTime
  }
  async resume() {}
  async decodeAudioData() {
    return { duration: chunkDurationSec }
  }
  createBufferSource() {
    return new FakeBufferSource()
  }
  createGain() {
    return { gain: { value: 1 }, connect() {} }
  }
}

// Captures the socket useVoiceOutput opens so tests can push server frames.
let lastSocket: FakeWebSocket | null = null

class FakeWebSocket {
  static OPEN = 1
  readyState = 1
  onopen: (() => void) | null = null
  onerror: ((e: unknown) => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  constructor(_url: string) {
    lastSocket = this
    setTimeout(() => this.onopen?.(), 0)
  }
  send() {}
  close() {}
}

const B64 = btoa('fake-audio-bytes')

type VoiceOutputModule = typeof import('../useVoiceOutput')
let useVoiceOutput: VoiceOutputModule['useVoiceOutput']

/** Push a server frame through the captured socket. */
function serverSend(msg: Record<string, unknown>): void {
  lastSocket?.onmessage?.({ data: JSON.stringify(msg) })
}

/** Deliver one audio chunk `advanceMs` after the previous one. */
async function sendChunk(advanceMs = 1000): Promise<void> {
  clockMs += advanceMs
  serverSend({ type: 'tts_audio', data: B64, chunk: 1 })
  // A macrotask boundary drains the whole decode/schedule microtask chain.
  await new Promise((resolve) => setTimeout(resolve, 0))
}

/**
 * Run one utterance whose chunks arrive at `rtf` audio-seconds per wall-second,
 * so the composable carries that production rate into the next utterance.
 */
async function calibrate(rtf: number, chunks = 3): Promise<void> {
  serverSend({ type: 'tts_start', text: 'calibration utterance' })
  await sendChunk(0)
  for (let i = 1; i < chunks; i++) {
    await sendChunk((chunkDurationSec / rtf) * 1000)
  }
  serverSend({ type: 'tts_end' })
}

describe('useVoiceOutput — adaptive pre-roll for a below-real-time worker (#12460)', () => {
  let originalAudioContext: unknown
  let originalWebSocket: unknown

  beforeEach(async () => {
    clockMs += 60_000
    ctxTime = 0
    chunkDurationSec = 0.25
    scheduledStarts = 0
    lastSocket = null
    vi.spyOn(Date, 'now').mockImplementation(() => clockMs)
    originalAudioContext = (globalThis as Record<string, unknown>).AudioContext
    originalWebSocket = (globalThis as Record<string, unknown>).WebSocket
    ;(globalThis as Record<string, unknown>).AudioContext = FakeAudioContext
    ;(globalThis as Record<string, unknown>).WebSocket = FakeWebSocket

    // Fresh module instance per test: the measured production rate is carried in
    // module state by design, so tests must not inherit each other's.
    vi.resetModules()
    const mod = await import('../useVoiceOutput')
    useVoiceOutput = mod.useVoiceOutput

    // Open the socket the composable owns.
    const unsubscribe = useVoiceOutput().subscribeVoiceMessages(() => {})
    await vi.waitFor(() => expect(lastSocket).not.toBeNull())
    unsubscribe()
  })

  afterEach(() => {
    useVoiceOutput().stopSpeaking()
    ;(globalThis as Record<string, unknown>).AudioContext = originalAudioContext
    ;(globalThis as Record<string, unknown>).WebSocket = originalWebSocket
    vi.restoreAllMocks()
  })

  it('holds nothing on the first utterance — no measured rate, so first-audio latency is unchanged', async () => {
    serverSend({ type: 'tts_start', text: 'a reasonably long first sentence to speak' })
    await sendChunk(0)
    expect(scheduledStarts).toBe(1)
    await sendChunk(4000)
    expect(scheduledStarts).toBe(2)
  })

  it('pre-rolls the next utterance once the worker is measured below real time', async () => {
    // 0.25x: 0.25s of audio per 1s of wall clock.
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    // Let the calibration audio finish so it contributes no lead-in.
    ctxTime = 1000

    // 20 chars * 0.06 s/char = 1.2s estimated audio; target = (1 - 0.25) * 1.2 = 0.9s.
    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    await sendChunk(1000)
    await sendChunk(1000)
    // 0.75s buffered — still short of the 0.9s lead-in, so nothing plays yet.
    expect(scheduledStarts).toBe(scheduledAfterCalibration)

    await sendChunk(1000)
    // 1.0s buffered clears the target: every held chunk is released at once.
    expect(scheduledStarts).toBe(scheduledAfterCalibration + 4)
  })

  it('flushes the tail on tts_end even when the lead-in target was never reached', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    await sendChunk(1000)
    expect(scheduledStarts).toBe(scheduledAfterCalibration)

    serverSend({ type: 'tts_end' })
    expect(scheduledStarts).toBe(scheduledAfterCalibration + 2)
  })

  it('drops held audio on stopSpeaking() so barge-in is immediate', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    await sendChunk(1000)
    expect(scheduledStarts).toBe(scheduledAfterCalibration)

    useVoiceOutput().stopSpeaking()
    serverSend({ type: 'tts_end' })
    // The superseded reply is never spoken, not even by the tail flush.
    expect(scheduledStarts).toBe(scheduledAfterCalibration)
  })

  it('does not pre-roll when the worker sustains real time', async () => {
    // 2x: audio is produced twice as fast as it plays, so no lead-in is needed.
    await calibrate(2.0)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    expect(scheduledStarts).toBe(scheduledAfterCalibration + 1)
  })

  it('counts audio still scheduled ahead as lead-in, so a follow-on sentence is not delayed twice', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    // The playhead has not moved, so the calibration utterance's 3 x 0.25s are
    // still queued ahead of it — 0.75s of real lead-in the next sentence inherits.
    ctxTime = 0

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    // 0.75s ahead + this 0.25s chunk clears the 0.9s target on the FIRST chunk,
    // instead of waiting out the full lead-in a second time.
    await sendChunk(0)
    expect(scheduledStarts).toBe(scheduledAfterCalibration + 1)
  })
})
