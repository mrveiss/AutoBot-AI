// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// useVoiceOutput zero-voices UX (#9999): when a deployment has no TTS voices,
// speak()/speakStreaming() must surface a user-visible toast instead of
// failing silently.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

const mockShowToast = vi.fn()
const mockFetchVoices = vi.fn()
const voicesRef = ref<Array<{ id: string }>>([])

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
    voices: voicesRef,
    fetchVoices: mockFetchVoices,
    effectiveVoiceId: ref(''),
  }),
}))

vi.mock('@/composables/usePreferences', () => ({
  usePreferences: () => ({ language: ref('en') }),
}))

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
  getBackendWsUrl: () => 'ws://test',
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}))

import { useVoiceOutput } from '../useVoiceOutput'
import { fetchWithAuth } from '@/utils/fetchWithAuth'

// The composable suppresses repeat "no voices" toasts within a 30s cooldown
// keyed on Date.now(). Advance a monotonic clock well past that window before
// each test so each test reliably surfaces (or asserts the absence of) a toast.
let _clock = 10_000_000

describe('useVoiceOutput — zero-voices UX (#9999)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    voicesRef.value = []
    mockFetchVoices.mockResolvedValue(undefined)
    _clock += 60_000 // jump past the notify cooldown
    vi.spyOn(Date, 'now').mockImplementation(() => _clock)
  })

  it('speak() surfaces a warning toast and does not call synthesize when no voices', async () => {
    const { speak } = useVoiceOutput()

    await speak('hello world', true)

    expect(mockShowToast).toHaveBeenCalledTimes(1)
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.stringContaining('Text-to-speech is not available'),
      'warning',
    )
    expect(fetchWithAuth).not.toHaveBeenCalled()
  })

  it('speak() lazily fetches voices before deciding there are none', async () => {
    const { speak } = useVoiceOutput()

    await speak('hello', true)

    expect(mockFetchVoices).toHaveBeenCalled()
  })

  it('speakStreaming() surfaces a warning toast when no voices', async () => {
    const { speakStreaming } = useVoiceOutput()

    await speakStreaming('hello world')

    expect(mockShowToast).toHaveBeenCalledWith(
      expect.stringContaining('Text-to-speech is not available'),
      'warning',
    )
  })

  it('speak() proceeds to synthesize when at least one voice is available', async () => {
    voicesRef.value = [{ id: 'v1' }]
    ;(fetchWithAuth as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 500,
    })

    const { speak } = useVoiceOutput()
    await speak('hello', true)

    expect(fetchWithAuth).toHaveBeenCalled()
    expect(mockShowToast).not.toHaveBeenCalled()
  })
})

// #11802: per-sentence streaming fires several speak() calls at once. Each
// voice check used to call fetchVoices() independently and useApiResource's
// `abortPrior` default cancelled the previous in-flight request, so the checks
// aborted each other (nginx 499), left `voices` empty, and surfaced the "no
// voices" toast on a deployment whose voices were fine.
describe('useVoiceOutput — concurrent voice checks (#11802)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    voicesRef.value = []
    _clock += 60_000
    vi.spyOn(Date, 'now').mockImplementation(() => _clock)
  })

  it('concurrent speak() calls share ONE voices fetch (no self-aborting race)', async () => {
    let resolveFetch: () => void = () => {}
    mockFetchVoices.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveFetch = () => {
            voicesRef.value = [{ id: 'v1' }]
            resolve()
          }
        }),
    )
    ;(fetchWithAuth as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 500,
    })

    const { speak } = useVoiceOutput()
    const inFlight = [speak('one', true), speak('two', true), speak('three', true)]
    resolveFetch()
    await Promise.all(inFlight)

    expect(mockFetchVoices).toHaveBeenCalledTimes(1)
    expect(mockShowToast).not.toHaveBeenCalled()
  })

  it('does not claim "no voices" when the fetch itself fails', async () => {
    mockFetchVoices.mockRejectedValue(new Error('aborted'))

    const { speak } = useVoiceOutput()
    await speak('hello', true)

    expect(mockShowToast).not.toHaveBeenCalled()
  })
})


// #12502: when the TTS WebSocket is unavailable, speakStreaming() falls back to
// per-sentence HTTP synthesis. Previously each fallback went through speak(),
// which aborts the in-flight utterance — so only the LAST sentence of a reply
// was heard. The fallback must now QUEUE sentences and play them sequentially
// without aborting each other.
describe('useVoiceOutput — sequential fallback queue (#12502)', () => {
  let originalAudioContext: unknown
  let originalWebSocket: unknown
  let bufferSourcesCreated = 0

  beforeEach(() => {
    vi.clearAllMocks()
    _clock += 60_000
    vi.spyOn(Date, 'now').mockImplementation(() => _clock)
    voicesRef.value = [{ id: 'v1' }]
    bufferSourcesCreated = 0

    class FakeBufferSource {
      buffer: unknown = null
      onended: (() => void) | null = null
      connect() {}
      start() {
        setTimeout(() => this.onended && this.onended(), 0)
      }
      stop() {}
    }
    class FakeAudioContext {
      state = 'running'
      currentTime = 0
      destination = {}
      async resume() {}
      async decodeAudioData() {
        return { duration: 0.05 }
      }
      createBufferSource() {
        bufferSourcesCreated++
        return new FakeBufferSource()
      }
      createGain() {
        return { gain: { value: 1 }, connect() {} }
      }
    }
    // A WebSocket that always fails to connect, forcing the HTTP fallback path.
    class FailingWebSocket {
      static OPEN = 1
      onopen: ((e?: unknown) => void) | null = null
      onerror: ((e?: unknown) => void) | null = null
      onclose: ((e?: unknown) => void) | null = null
      onmessage: ((e?: unknown) => void) | null = null
      readyState = 0
      constructor() {
        setTimeout(() => this.onerror && this.onerror(new Event('error')), 0)
      }
      send() {}
      close() {}
    }

    originalAudioContext = (globalThis as Record<string, unknown>).AudioContext
    originalWebSocket = (globalThis as Record<string, unknown>).WebSocket
    ;(globalThis as Record<string, unknown>).AudioContext = FakeAudioContext
    ;(globalThis as Record<string, unknown>).WebSocket = FailingWebSocket
  })

  afterEach(() => {
    ;(globalThis as Record<string, unknown>).AudioContext = originalAudioContext
    ;(globalThis as Record<string, unknown>).WebSocket = originalWebSocket
  })

  it('queues every fallback sentence and plays them all — none aborted', async () => {
    const signals: AbortSignal[] = []
    const texts: string[] = []
    ;(fetchWithAuth as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async (_url: string, opts: { body: FormData; signal: AbortSignal }) => {
        signals.push(opts.signal)
        texts.push(String(opts.body.get('text')))
        return {
          ok: true,
          status: 200,
          // #13215: a real Response always has headers; without the framing
          // marker the client takes the whole-blob path these tests cover.
          headers: { get: () => null },
          body: null,
          blob: async () => ({ arrayBuffer: async () => new ArrayBuffer(8) }),
        }
      },
    )

    const { speakStreaming } = useVoiceOutput()
    const sentences = [
      'First sentence of the streamed reply.',
      'Second sentence of the streamed reply.',
      'Third sentence of the streamed reply.',
    ]
    // Dispatch per-sentence exactly like the streaming watcher (not awaited).
    sentences.forEach((s) => {
      void speakStreaming(s)
    })

    // Let the WS reject, the queue drain, and every playback complete.
    await vi.waitFor(() => {
      expect(texts.length).toBe(sentences.length)
      expect(bufferSourcesCreated).toBe(sentences.length)
    })

    // Every sentence was synthesized — none dropped by a self-aborting fallback.
    expect([...texts].sort()).toEqual([...sentences].sort())
    // All were actually played to completion (one audio buffer each).
    expect(bufferSourcesCreated).toBe(sentences.length)
    // Critically: NO in-flight utterance was aborted by a later fallback call
    // (the pre-fix speak() path aborted the previous one every time).
    expect(signals.some((s) => s.aborted)).toBe(false)
  })

  it('stopSpeaking() clears the fallback queue and aborts the in-flight utterance', async () => {
    const signals: AbortSignal[] = []
    let releaseFirst: () => void = () => {}
    ;(fetchWithAuth as unknown as ReturnType<typeof vi.fn>).mockImplementation(
      async (_url: string, opts: { signal: AbortSignal }) => {
        signals.push(opts.signal)
        // Block the first synthesis so we can stop mid-flight.
        await new Promise<void>((resolve) => {
          releaseFirst = resolve
        })
        return {
          ok: true,
          status: 200,
          // #13215: a real Response always has headers; without the framing
          // marker the client takes the whole-blob path these tests cover.
          headers: { get: () => null },
          body: null,
          blob: async () => ({ arrayBuffer: async () => new ArrayBuffer(8) }),
        }
      },
    )

    const { speakStreaming, stopSpeaking } = useVoiceOutput()
    void speakStreaming('First blocked sentence of the reply.')
    void speakStreaming('Second queued sentence of the reply.')
    void speakStreaming('Third queued sentence of the reply.')

    // Wait until the first synthesis is in-flight.
    await vi.waitFor(() => {
      expect(signals.length).toBe(1)
    })

    // User-initiated stop must abort the in-flight request and drop the queue.
    stopSpeaking()
    releaseFirst()

    // Give any (incorrectly) queued follow-ups a chance to fire.
    await new Promise((r) => setTimeout(r, 20))

    expect(signals[0].aborted).toBe(true)
    // No further synthesis started after the stop — queue was cleared.
    expect(signals.length).toBe(1)
  })
})
