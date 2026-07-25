// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #12503: the WS streaming path plays TTS via _playAudioChunkFromBase64 →
// _scheduleGaplessChunk. Two client bugs made voice output show the "AutoBot
// speaking" indicator with NO sound and often leave it stuck:
//   (1) the AudioContext was never resumed on a user gesture, so a suspended
//       context outside a gesture silenced every scheduled buffer, and
//   (2) isSpeaking was set BEFORE playback, so a never-playing chunk left the
//       indicator on forever.
// These tests exercise the exact streaming playback path (playAudioChunk) and
// assert the context is resumed before playback and isSpeaking tracks REAL
// audio (set on start, cleared on end/stop/failure).

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

const mockShowToast = vi.fn()

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    showToast: mockShowToast,
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

import { useVoiceOutput } from '../useVoiceOutput'

// ── Controllable fake Web Audio, driven by module-scope lets so the retained
// singleton AudioContext reads current values via getters between tests. ──
let ctxState: 'running' | 'suspended' = 'running'
let resumeMakesRunning = true
let decodeShouldThrow = false
let resumeCalls = 0
let scheduledStarts = 0
let pendingEnded: Array<() => void> = []

class FakeBufferSource {
  buffer: unknown = null
  onended: (() => void) | null = null
  connect() {}
  start() {
    scheduledStarts++
    // Defer onended so a chunk is "playing" until the test flushes it.
    pendingEnded.push(() => this.onended && this.onended())
  }
  stop() {}
}

class FakeAudioContext {
  currentTime = 0
  destination = {}
  get state() {
    return ctxState
  }
  async resume() {
    resumeCalls++
    if (resumeMakesRunning) ctxState = 'running'
  }
  async decodeAudioData() {
    if (decodeShouldThrow) throw new Error('decode failed')
    return { duration: 0.05 }
  }
  createBufferSource() {
    return new FakeBufferSource()
  }
  createGain() {
    return { gain: { value: 1 }, connect() {} }
  }
}

function flushEnded() {
  const cbs = pendingEnded
  pendingEnded = []
  cbs.forEach((cb) => cb())
}

// A valid base64 WAV-ish payload; bytes are irrelevant since decode is faked.
const B64 = btoa('fake-audio-bytes')

let _clock = 20_000_000
let originalAudioContext: unknown

describe('useVoiceOutput — streaming playback unlock + isSpeaking (#12503)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    ctxState = 'running'
    resumeMakesRunning = true
    decodeShouldThrow = false
    resumeCalls = 0
    scheduledStarts = 0
    pendingEnded = []
    _clock += 60_000
    vi.spyOn(Date, 'now').mockImplementation(() => _clock)
    originalAudioContext = (globalThis as Record<string, unknown>).AudioContext
    ;(globalThis as Record<string, unknown>).AudioContext = FakeAudioContext
  })

  afterEach(() => {
    // Reset shared module state (isSpeaking, scheduling, armed gesture listener).
    const { stopSpeaking, unlockAudio } = useVoiceOutput()
    stopSpeaking()
    unlockAudio()
    ;(globalThis as Record<string, unknown>).AudioContext = originalAudioContext
    vi.restoreAllMocks()
  })

  it('sets isSpeaking only once a buffer is scheduled, and clears it when playback ends', async () => {
    const { playAudioChunk, isSpeaking } = useVoiceOutput()

    expect(isSpeaking.value).toBe(false)
    playAudioChunk(B64)
    // Let the async decode/schedule microtasks settle.
    await vi.waitFor(() => expect(scheduledStarts).toBe(1))

    // Indicator reflects real, scheduled audio.
    expect(isSpeaking.value).toBe(true)

    // When the source finishes, the indicator clears.
    flushEnded()
    expect(isSpeaking.value).toBe(false)
  })

  it('resumes a suspended AudioContext before scheduling playback', async () => {
    ctxState = 'suspended'
    resumeMakesRunning = true // gesture-equivalent: resume actually unlocks

    const { playAudioChunk, isSpeaking } = useVoiceOutput()
    playAudioChunk(B64)

    await vi.waitFor(() => expect(scheduledStarts).toBe(1))
    // resume() was awaited BEFORE the buffer was scheduled/started.
    expect(resumeCalls).toBeGreaterThanOrEqual(1)
    expect(isSpeaking.value).toBe(true)
  })

  it('does NOT set isSpeaking (no stuck indicator) when the context stays suspended, and arms a gesture unlock + hint', async () => {
    ctxState = 'suspended'
    resumeMakesRunning = false // resume() cannot unlock outside a user gesture
    const addSpy = vi.spyOn(window, 'addEventListener')

    const { playAudioChunk, isSpeaking } = useVoiceOutput()
    playAudioChunk(B64)

    // Wait until the suspended-path bailout runs (hint surfaced after resume()).
    await vi.waitFor(() => expect(mockShowToast).toHaveBeenCalled())
    expect(resumeCalls).toBeGreaterThanOrEqual(1)
    // No buffer was scheduled (context still suspended) → no audio.
    expect(scheduledStarts).toBe(0)
    // Critically: the indicator is NOT stuck on.
    expect(isSpeaking.value).toBe(false)
    // A one-time gesture listener was armed to unlock on the next interaction.
    const armedGestureEvents = addSpy.mock.calls.map((c) => c[0])
    expect(armedGestureEvents).toContain('pointerdown')
    // And a "tap to enable audio" hint was surfaced.
    expect(mockShowToast).toHaveBeenCalledWith(expect.any(String), 'info')
  })

  it('clears isSpeaking when a scheduled chunk fails to decode', async () => {
    decodeShouldThrow = true

    const { playAudioChunk, isSpeaking } = useVoiceOutput()
    playAudioChunk(B64)

    // Decode rejects; the awaited/caught path must not leave the indicator stuck.
    await vi.waitFor(() => expect(isSpeaking.value).toBe(false))
    expect(scheduledStarts).toBe(0)
  })

  it('stopSpeaking() clears isSpeaking mid-playback', async () => {
    const { playAudioChunk, stopSpeaking, isSpeaking } = useVoiceOutput()
    playAudioChunk(B64)
    await vi.waitFor(() => expect(isSpeaking.value).toBe(true))

    stopSpeaking()
    expect(isSpeaking.value).toBe(false)
  })
})
