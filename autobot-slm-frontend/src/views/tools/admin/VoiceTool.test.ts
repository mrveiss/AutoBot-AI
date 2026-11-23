// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import VoiceTool from './VoiceTool.vue'
import { backendClient } from '@/testing/mockAutobotBackendClient'
import en from '@/locales/en.json'

/**
 * `POST /voice/speak` answers `audio/wav` (#17779). The tool used to parse that as JSON and read two
 * fields it never had, so every success showed "No response received" (#17784). These drive the
 * success path through a stubbed recogniser and assert the audio is fetched and played, with no role sent (#22143).
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ token: 'test-token' }) }))
vi.mock('@/utils/ApiClient', async (importOriginal) =>
  (await import('@/testing/mockAutobotBackendClient')).withMockedBackendClient(importOriginal),
)

const i18n = createI18n({ legacy: true, locale: 'en', fallbackLocale: 'en', messages: { en } })

const play = vi.fn().mockResolvedValue(undefined)

class FakeRecognition {
  static last: FakeRecognition | null = null
  continuous = false
  interimResults = false
  lang = ''
  onstart: (() => void) | null = null
  onresult: ((e: unknown) => void) | null = null
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  start(): void {
    FakeRecognition.last = this
    this.onstart?.()
  }
  stop(): void {}
  abort(): void {}
}

class FakeAudio {
  playbackRate = 1
  onplay: (() => void) | null = null
  onended: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(public src: string) {}
  play = play
  pause(): void {}
}

async function dictate(text: string) {
  const wrapper = mount(VoiceTool, { global: { plugins: [i18n] } })
  await wrapper.get('button').trigger('click')
  FakeRecognition.last?.onresult?.({ resultIndex: 0, results: { length: 1, 0: { isFinal: true, 0: { transcript: text } } } })
  FakeRecognition.last?.onend?.()
  await flushPromises()
  return wrapper
}

describe('VoiceTool speaks the transcript through the audio route', () => {
  beforeEach(() => {
    vi.stubGlobal('webkitSpeechRecognition', FakeRecognition)
    vi.stubGlobal('Audio', FakeAudio)
    URL.createObjectURL = vi.fn(() => 'blob:test')
    URL.revokeObjectURL = vi.fn()
    backendClient.rawRequest.mockReset()
    play.mockClear()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('plays the returned audio and never shows the old fallback', async () => {
    backendClient.rawRequest.mockResolvedValue(new Response(new Blob(['RIFF'], { type: 'audio/wav' }), { status: 200 }))
    const wrapper = await dictate('hello there')

    const [path, options] = backendClient.rawRequest.mock.calls[0]
    expect(path).toBe('/voice/speak')
    expect((options.body as FormData).get('text')).toBe('hello there')
    expect((options.body as FormData).has('user_role')).toBe(false)
    expect(play).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('hello there')
    expect(wrapper.text()).not.toContain('No response received')
  })

  it('shows the localised failure with the status, and plays nothing, when the route refuses', async () => {
    backendClient.rawRequest.mockResolvedValue(
      new Response(JSON.stringify({ message: 'Permission denied to speak via voice.' }), {
        status: 403,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const wrapper = await dictate('hello')
    expect(play).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain(en.tools.admin.voiceTool.speakFailed)
    expect(wrapper.text()).toContain('403')
  })
})
