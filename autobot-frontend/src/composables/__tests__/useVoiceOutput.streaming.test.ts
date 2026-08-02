// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// #13215: the HTTP TTS path waited for the whole utterance before any audio
// existed (measured 4.7-10.1s to first sound). The backend now emits
// `[4-byte big-endian length][WAV]` frames when `stream=true` is requested;
// these tests assert the client actually asks for that, splits the frames, and
// schedules each mini-WAV as it arrives rather than after the stream ends.
//
// Splitting matters: the chunks are separate, independently-decodable WAV
// files, so handing the concatenated body to decodeAudioData would decode only
// the first one and silently drop the rest of the sentence.

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

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { useVoiceOutput } from '../useVoiceOutput'

const FRAMING_HEADER = 'X-Audio-Framing'
const FRAMING_VALUE = 'length-prefixed-wav'

const CHUNKS = [
  new Uint8Array([1, 1, 1, 1]),
  new Uint8Array([2, 2, 2, 2, 2, 2]),
  new Uint8Array([3, 3]),
]

let decodedSizes: number[] = []
let scheduledStarts = 0

class FakeBufferSource {
  buffer: unknown = null
  onended: (() => void) | null = null
  connect() {}
  start() {
    scheduledStarts++
    // Playback "completes" on the next macrotask so the whole-blob path, which
    // awaits onended, resolves without the test having to drive it by hand.
    setTimeout(() => this.onended && this.onended(), 0)
  }
  stop() {}
}

class FakeAudioContext {
  currentTime = 0
  destination = {}
  state = 'running'
  async resume() {}
  async decodeAudioData(buf: ArrayBuffer) {
    decodedSizes.push(buf.byteLength)
    return { duration: 0.05 }
  }
  createBufferSource() {
    return new FakeBufferSource()
  }
  createGain() {
    return { gain: { value: 1 }, connect() {} }
  }
}

/** Build the backend's `[4-byte length][WAV]` framing for `chunks`. */
function frame(chunks: Uint8Array[]): Uint8Array[] {
  return chunks.map((c) => {
    const out = new Uint8Array(4 + c.length)
    new DataView(out.buffer).setUint32(0, c.length, false)
    out.set(c, 4)
    return out
  })
}

/**
 * A ReadableStream that emits `pieces` one at a time and records, per piece,
 * how many buffers had already been scheduled — proving playback starts before
 * the response finishes rather than after it.
 */
function pacedStream(pieces: Uint8Array[], scheduledWhenEmitted: number[]): ReadableStream<Uint8Array> {
  let index = 0
  return new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (index >= pieces.length) {
        controller.close()
        return
      }
      scheduledWhenEmitted.push(scheduledStarts)
      controller.enqueue(pieces[index])
      index += 1
    },
  })
}

function streamResponse(body: ReadableStream<Uint8Array>): Response {
  return {
    ok: true,
    status: 200,
    headers: { get: (name: string) => (name === FRAMING_HEADER ? FRAMING_VALUE : null) },
    body,
    blob: async () => {
      throw new Error('blob() must not be used on a framed response')
    },
  } as unknown as Response
}

let originalAudioContext: unknown

describe('useVoiceOutput — chunked HTTP synthesis (#13215)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    decodedSizes = []
    scheduledStarts = 0
    originalAudioContext = (globalThis as Record<string, unknown>).AudioContext
    ;(globalThis as Record<string, unknown>).AudioContext = FakeAudioContext
  })

  afterEach(() => {
    const { stopSpeaking } = useVoiceOutput()
    stopSpeaking()
    ;(globalThis as Record<string, unknown>).AudioContext = originalAudioContext
    vi.restoreAllMocks()
  })

  it('requests the chunked variant and schedules each frame separately', async () => {
    const emitted: number[] = []
    vi.mocked(fetchWithAuth).mockResolvedValue(streamResponse(pacedStream(frame(CHUNKS), emitted)))

    const { speak } = useVoiceOutput()
    await speak('hello there', true)

    const [, init] = vi.mocked(fetchWithAuth).mock.calls[0]
    expect((init?.body as FormData).get('stream')).toBe('true')
    expect(decodedSizes).toEqual(CHUNKS.map((c) => c.length))
    expect(scheduledStarts).toBe(CHUNKS.length)
  })

  it('plays the first chunk before the response has finished arriving', async () => {
    const emitted: number[] = []
    vi.mocked(fetchWithAuth).mockResolvedValue(streamResponse(pacedStream(frame(CHUNKS), emitted)))

    const { speak } = useVoiceOutput()
    await speak('hello there', true)

    // The final piece was requested only after earlier chunks were already
    // scheduled — i.e. audio started while bytes were still in flight. A
    // buffer-then-play implementation reports 0 here for every piece.
    expect(emitted[emitted.length - 1]).toBeGreaterThan(0)
  })

  it('splits frames correctly when they arrive misaligned across reads', async () => {
    const framed = frame(CHUNKS)
    const joined = new Uint8Array(framed.reduce((n, f) => n + f.length, 0))
    let offset = 0
    for (const f of framed) {
      joined.set(f, offset)
      offset += f.length
    }
    // Split at byte 3 — mid-header — so a naive per-read parser mis-frames.
    const pieces = [joined.slice(0, 3), joined.slice(3, 9), joined.slice(9)]
    vi.mocked(fetchWithAuth).mockResolvedValue(streamResponse(pacedStream(pieces, [])))

    const { speak } = useVoiceOutput()
    await speak('hello there', true)

    expect(decodedSizes).toEqual(CHUNKS.map((c) => c.length))
  })

  it('falls back to whole-blob playback when the response is not framed', async () => {
    const wav = new Uint8Array([9, 9, 9, 9, 9])
    vi.mocked(fetchWithAuth).mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => null },
      body: null,
      blob: async () => ({ arrayBuffer: async () => wav.buffer }),
    } as unknown as Response)

    const { speak } = useVoiceOutput()
    await speak('hello there', true)

    expect(decodedSizes).toEqual([wav.length])
  })
})
