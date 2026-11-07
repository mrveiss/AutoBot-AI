// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// wavesurfer.js v8 rejects a load that a newer one supersedes, with AbortError, where v7
// resolved it quietly. `WaveformPlayer.vue` calls `init` from `onMounted` and from a `watch`
// on the url, and neither awaits the promise it returns, so before the guard a user switching
// recording mid-load produced an unhandled rejection.
//
// The existing transcriber test STUBS the whole player because it dynamically imports
// wavesurfer in jsdom, so nothing in the suite exercised this. That is why the bump could
// have landed green: the library CI would have to break is the one the tests replace.
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'

const loadImpl = vi.fn()

vi.mock('wavesurfer.js', () => ({
  default: {
    create: () => ({
      on: vi.fn(),
      load: loadImpl,
      destroy: vi.fn(),
      getDuration: () => 0,
      seekTo: vi.fn(),
      playPause: vi.fn(),
    }),
  },
}))

// Imported after the mock so the dynamic import inside resolves to it.
const { useWaveform } = await import('@/composables/transcriber/useWaveform')

function abortError(): Error {
  const err = new Error('load aborted')
  err.name = 'AbortError'
  return err
}

describe('useWaveform load supersession (wavesurfer v8)', () => {
  it('swallows the AbortError of a load a newer one superseded', async () => {
    loadImpl.mockRejectedValueOnce(abortError())
    const { init } = useWaveform(ref(document.createElement('div')))

    await expect(init('/audio/first.wav')).resolves.toBeUndefined()
  })

  it('still raises any other load failure', async () => {
    // The contrast pair. A guard that swallowed everything would pass the case above
    // while hiding a genuinely broken audio URL.
    loadImpl.mockRejectedValueOnce(new Error('404 fetching audio'))
    const { init } = useWaveform(ref(document.createElement('div')))

    await expect(init('/audio/missing.wav')).rejects.toThrow('404 fetching audio')
  })

  it('resolves normally when the load succeeds', async () => {
    loadImpl.mockResolvedValueOnce(undefined)
    const { init } = useWaveform(ref(document.createElement('div')))

    await expect(init('/audio/ok.wav')).resolves.toBeUndefined()
  })
})
