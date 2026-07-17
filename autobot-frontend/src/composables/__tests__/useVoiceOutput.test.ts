// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// useVoiceOutput zero-voices UX (#9999): when a deployment has no TTS voices,
// speak()/speakStreaming() must surface a user-visible toast instead of
// failing silently.

import { describe, it, expect, vi, beforeEach } from 'vitest'
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
