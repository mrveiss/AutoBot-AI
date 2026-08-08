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

// ── Controllable fakes ─────────────────────────────────────────────────────
let clockMs = 1_700_000_000_000
let ctxTime = 0
let ctxState: 'running' | 'suspended' = 'running'
let chunkDurationSec = 0.25
let scheduledStarts = 0
let liveSources: FakeBufferSource[] = []

class FakeBufferSource {
  buffer: unknown = null
  onended: (() => void) | null = null
  connect() {}
  start() {
    scheduledStarts++
    // Stays "playing" until a test ends it, mirroring a real source node.
    liveSources.push(this)
  }
  stop() {}
}

/** Finish every scheduled source, as the real timeline would on playout. */
function endAllScheduled(): void {
  const sources = liveSources
  liveSources = []
  for (const source of sources) source.onended?.()
}

class FakeAudioContext {
  destination = {}
  get state() {
    return ctxState
  }
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
  constructor() {
    setTimeout(() => this.onopen?.(), 0)
  }
  send() {}
  close() {}
}

// Constructed through a factory rather than recording `this` inside the
// constructor, which trips oxlint's no-this-alias. `new` on a function that
// returns an object yields that object, so the composable's `new WebSocket(url)`
// still gets a FakeWebSocket.
function FakeWebSocketFactory(): FakeWebSocket {
  const socket = new FakeWebSocket()
  lastSocket = socket
  return socket
}
FakeWebSocketFactory.OPEN = 1

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
    ctxState = 'running'
    chunkDurationSec = 0.25
    scheduledStarts = 0
    liveSources = []
    lastSocket = null
    vi.spyOn(Date, 'now').mockImplementation(() => clockMs)
    originalAudioContext = (globalThis as Record<string, unknown>).AudioContext
    originalWebSocket = (globalThis as Record<string, unknown>).WebSocket
    ;(globalThis as Record<string, unknown>).AudioContext = FakeAudioContext
    ;(globalThis as Record<string, unknown>).WebSocket = FakeWebSocketFactory

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

  it('credits scheduled-ahead audio at the production rate, not at its full duration', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    // The playhead has not moved, so the calibration utterance's 3 x 0.25s are
    // still queued ahead of it: A = 0.75s.
    ctxTime = 0

    // Target is 0.9s. While those 0.75s play out the worker adds only r*A =
    // 0.1875s, NOT 0.75s — crediting A at full value would release here, one
    // chunk in, with 0.25s buffered against a 1.2s utterance, and starve.
    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    expect(scheduledStarts).toBe(scheduledAfterCalibration)
    await sendChunk(1000)
    expect(scheduledStarts).toBe(scheduledAfterCalibration)

    // 0.75s buffered + 0.1875s credited clears 0.9s — one chunk sooner than the
    // four needed with no audio queued ahead, which is the real benefit.
    await sendChunk(1000)
    expect(scheduledStarts).toBe(scheduledAfterCalibration + 3)
  })

  it('keeps isSpeaking true while holding, so the mic is not reopened mid-reply', async () => {
    await calibrate(0.25)
    ctxTime = 1000
    endAllScheduled()
    const { isSpeaking } = useVoiceOutput()
    // Calibration audio has played out; nothing is sounding.
    expect(isSpeaking.value).toBe(false)

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)

    // The reply is buffering, not finished. A false here fires
    // watch(isSpeaking) in useVoiceConversation, which expires the TTS echo
    // cooldown and reopens the mic while AutoBot is still about to speak.
    expect(isSpeaking.value).toBe(true)
  })

  it('starts speaking within the wait budget rather than buffering indefinitely', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000
    endAllScheduled()

    // Chunks trickle in every 4s (0.0625x live). The wall-clock bound caps the
    // target at MAX_WAIT*r, so the buffer that must accumulate is small and
    // speech starts inside the budget instead of after the whole reply.
    serverSend({ type: 'tts_start', text: 'x'.repeat(180) })
    const before = clockMs
    await sendChunk(0)
    await sendChunk(4000)
    await sendChunk(4000)

    expect(scheduledStarts).toBeGreaterThan(scheduledAfterCalibration)
    // Because the wait is bounded at 8s and the stall watchdog only fires after
    // 10s of silence, filling the lead-in can never outlast the watchdog — so
    // it can only ever fire on a genuine stall, never as a duration cap.
    expect(clockMs - before).toBeLessThanOrEqual(8000)
  })

  it('releases held audio when the worker genuinely stalls', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000

    vi.useFakeTimers()
    try {
      serverSend({ type: 'tts_start', text: 'x'.repeat(180) })
      clockMs += 1000
      serverSend({ type: 'tts_audio', data: B64, chunk: 0 })
      await vi.advanceTimersByTimeAsync(1)
      expect(scheduledStarts).toBe(scheduledAfterCalibration)

      // No further chunk — the watchdog plays what is buffered rather than
      // stranding it.
      await vi.advanceTimersByTimeAsync(11_000)
      expect(scheduledStarts).toBe(scheduledAfterCalibration + 1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('bounds the WAIT, not just the buffer — a 0.09x worker must not buy 90s of silence', async () => {
    // 0.09x is the slowest rate measured in #12460.
    await calibrate(0.09)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000
    endAllScheduled()

    // A 180-char reply: the derived lead-in is (1 - 0.09) * 10.8s = 9.8s, capped
    // to 8 audio-seconds. Filling 8s at 0.09x would take ~90s of silence. The
    // wall-clock bound caps the buffer at MAX_WAIT*r = 0.72s instead.
    serverSend({ type: 'tts_start', text: 'x'.repeat(180) })
    await sendChunk(0)
    await sendChunk(2778)
    await sendChunk(2778)

    // 0.75s buffered clears the 0.72s bound: speech starts inside the wait
    // budget rather than a minute and a half later.
    expect(scheduledStarts).toBe(scheduledAfterCalibration + 3)
  })

  it('a chunk decoded after its utterance ended is not folded into the next one', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000
    endAllScheduled()

    // Last chunk of utterance A is still decoding when tts_end and the next
    // tts_start arrive — the real ordering, since decodeAudioData is async.
    clockMs += 1000
    serverSend({ type: 'tts_audio', data: B64, chunk: 9 })
    serverSend({ type: 'tts_end' })
    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await new Promise((resolve) => setTimeout(resolve, 0))

    // It belongs to the reply already playing, so it goes straight to the
    // timeline instead of being held with — and skewing the rate of — utterance B.
    expect(scheduledStarts).toBe(scheduledAfterCalibration + 1)
  })

  it('recovers its target after a transient arrival gap instead of ratcheting to the cap', async () => {
    await calibrate(0.5)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000
    endAllScheduled()

    serverSend({ type: 'tts_start', text: 'x'.repeat(60) })
    await sendChunk(0)
    // One long stall, then the worker catches up at a healthy rate.
    await sendChunk(6000)
    for (let i = 0; i < 8; i++) await sendChunk(120)

    // The cumulative rate recovers, so the target falls back and the audio is
    // released. A one-way ratchet pinned it at the cap for the whole utterance.
    expect(scheduledStarts).toBeGreaterThan(scheduledAfterCalibration)
  })

  it('does not schedule held audio onto a context suspended during the hold', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000
    endAllScheduled()

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    await sendChunk(1000)

    // The tab was backgrounded while the reply buffered. Starting sources on a
    // frozen timeline never fires onended, which is how the indicator used to
    // stick (#12503) — take the gesture-unlock exit instead.
    ctxState = 'suspended'
    const { isSpeaking } = useVoiceOutput()
    serverSend({ type: 'tts_end' })

    expect(scheduledStarts).toBe(scheduledAfterCalibration)
    expect(isSpeaking.value).toBe(false)
    expect(mockShowToast).toHaveBeenCalledWith(expect.any(String), 'info')
  })

  it('keeps isSpeaking true when the previous sentence drains while the next pre-rolls', async () => {
    await calibrate(0.25)
    ctxTime = 1000
    const { isSpeaking } = useVoiceOutput()

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    expect(isSpeaking.value).toBe(true)

    // The previous sentence's audio finishes while this one is still buffering.
    // Clearing isSpeaking here fires watch(isSpeaking) in useVoiceConversation,
    // which reopens the mic in the gap between sentences.
    endAllScheduled()
    expect(isSpeaking.value).toBe(true)
  })

  it('ignores a nonsense rate from two chunks arriving coalesced', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000
    endAllScheduled()

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    // 2ms apart: a cumulative rate of ~125x. Trusting it drops the target to 0
    // and releases the pre-roll for the rest of the utterance.
    await sendChunk(2)
    expect(scheduledStarts).toBe(scheduledAfterCalibration)
  })

  it('drops chunks still decoding when a stop lands, so no fragment is spoken', async () => {
    await calibrate(2.0)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000
    endAllScheduled()
    const { isSpeaking, stopSpeaking } = useVoiceOutput()

    // Chunk dispatched, then barge-in before its decode resolves.
    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    clockMs += 100
    serverSend({ type: 'tts_audio', data: B64, chunk: 1 })
    stopSpeaking()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(scheduledStarts).toBe(scheduledAfterCalibration)
    expect(isSpeaking.value).toBe(false)
  })

  it('retains held audio across a suspend instead of losing the reply opening', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000
    endAllScheduled()

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    await sendChunk(1000)

    // Backgrounded mid-hold: the release cannot schedule, but the audio is the
    // opening of the reply and must survive until the context is unlocked.
    ctxState = 'suspended'
    serverSend({ type: 'tts_end' })
    expect(scheduledStarts).toBe(scheduledAfterCalibration)

    // Once unlocked, the retained audio still plays.
    ctxState = 'running'
    await sendChunk(1000)
    expect(scheduledStarts).toBeGreaterThan(scheduledAfterCalibration)
  })

  it('a superseded reply mid-hold is dropped by speak(), not spoken first', async () => {
    await calibrate(0.25)
    const scheduledAfterCalibration = scheduledStarts
    ctxTime = 1000

    serverSend({ type: 'tts_start', text: 'twenty chars exactly' })
    await sendChunk(0)
    await sendChunk(1000)
    expect(scheduledStarts).toBe(scheduledAfterCalibration)

    // A new one-shot utterance supersedes the held reply. speak()'s stop guard
    // must fire even though nothing is on the timeline yet, or _beginUtterance's
    // release speaks the superseded audio first — the #12502 failure.
    await useVoiceOutput().speak('a replacement utterance', true)

    expect(scheduledStarts).toBe(scheduledAfterCalibration)
  })
})
