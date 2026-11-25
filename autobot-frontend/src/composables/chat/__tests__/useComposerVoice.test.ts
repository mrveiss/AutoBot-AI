// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Behaviour parity for one-message dictation, moved out of ChatInput.vue (#18243): the transcript replaces
 * the draft while recording, a denied microphone is toasted, and a browser without the Web Speech API still
 * asks for the microphone before saying so.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope, ref } from 'vue'

const showToast = vi.hoisted(() => vi.fn())
vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k }),
}))
vi.mock('@autobot/ui', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@autobot/ui')>()),
  useToast: () => ({ showToast }),
}))

import { useComposerVoice } from '../useComposerVoice'

class FakeRecognition {
  static last: FakeRecognition | null = null
  continuous = true
  interimResults = false
  lang = ''
  onstart: (() => void) | null = null
  onresult: ((e: { results: unknown }) => void) | null = null
  onend: (() => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  start = vi.fn(() => this.onstart?.())
  stop = vi.fn()
  abort = vi.fn()
  constructor() { FakeRecognition.last = this }
}

const win = window as unknown as Record<string, unknown>

beforeEach(() => {
  showToast.mockReset()
  FakeRecognition.last = null
  win.SpeechRecognition = FakeRecognition
})
afterEach(() => {
  delete win.SpeechRecognition
  delete win.webkitSpeechRecognition
})

describe('useComposerVoice', () => {
  it('records one message: not continuous, interim results, and starts recording on start', () => {
    const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(ref(''))
    toggleVoiceInput()
    const rec = FakeRecognition.last!
    expect(rec.continuous).toBe(false)
    expect(rec.interimResults).toBe(true)
    expect(rec.lang).toBe('en-US')
    expect(isVoiceRecording.value).toBe(true)
  })

  it('writes the joined transcript over the draft', () => {
    const text = ref('old')
    useComposerVoice(text).toggleVoiceInput()
    FakeRecognition.last!.onresult!({ results: [[{ transcript: 'hello ' }], [{ transcript: 'world' }]] })
    expect(text.value).toBe('hello world')
  })

  it('stops on a second toggle', () => {
    const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(ref(''))
    toggleVoiceInput()
    toggleVoiceInput()
    expect(FakeRecognition.last!.stop).toHaveBeenCalledTimes(1)
    expect(isVoiceRecording.value).toBe(true) // sending stays blocked until the recogniser ends
    FakeRecognition.last!.onend!()
    expect(isVoiceRecording.value).toBe(false)
  })

  it('still takes the final transcript that arrives after Stop, before onend', () => {
    const text = ref('')
    const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(text)
    toggleVoiceInput()
    toggleVoiceInput()
    FakeRecognition.last!.onresult!({ results: [[{ transcript: 'final words' }]] })
    expect(text.value).toBe('final words')
    expect(isVoiceRecording.value).toBe(true)
  })

  it('clears the recording state when recognition ends', () => {
    const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(ref(''))
    toggleVoiceInput()
    FakeRecognition.last!.onend!()
    expect(isVoiceRecording.value).toBe(false)
  })

  it('toasts a denied microphone and stops recording', () => {
    const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(ref(''))
    toggleVoiceInput()
    FakeRecognition.last!.onerror!({ error: 'not-allowed' })
    expect(isVoiceRecording.value).toBe(false)
    expect(showToast).toHaveBeenCalledWith('chat.input.micDenied', 'error')
  })

  it('does not toast other recognition errors', () => {
    const { toggleVoiceInput } = useComposerVoice(ref(''))
    toggleVoiceInput()
    FakeRecognition.last!.onerror!({ error: 'no-speech' })
    expect(showToast).not.toHaveBeenCalled()
  })

  it('a toggle before onstart stops the pending recogniser instead of starting a second', () => {
    win.SpeechRecognition = class extends FakeRecognition { start = vi.fn() } // never reaches onstart
    const { toggleVoiceInput } = useComposerVoice(ref(''))
    toggleVoiceInput()
    const first = FakeRecognition.last!
    toggleVoiceInput()
    expect(FakeRecognition.last).toBe(first)
    expect(first.stop).toHaveBeenCalledTimes(1)
  })

  it('a start() that throws leaves no dead recogniser: it toasts and the next toggle starts again', () => {
    win.SpeechRecognition = class extends FakeRecognition {
      start = vi.fn(() => { throw new Error('InvalidStateError') })
    }
    const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(ref(''))
    toggleVoiceInput()
    const failed = FakeRecognition.last!
    expect(isVoiceRecording.value).toBe(false)
    expect(showToast).toHaveBeenCalledWith('chat.input.micDenied', 'error')
    toggleVoiceInput()
    expect(failed.stop).not.toHaveBeenCalled() // it started a new one rather than stopping the dead one
    expect(FakeRecognition.last).not.toBe(failed)
  })

  it('ignores callbacks of an older recogniser', () => {
    const text = ref('')
    const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(text)
    toggleVoiceInput()
    const old = FakeRecognition.last!
    old.onend!()
    toggleVoiceInput()
    expect(FakeRecognition.last).not.toBe(old)
    old.onend!()
    old.onresult!({ results: [[{ transcript: 'stale' }]] })
    expect(isVoiceRecording.value).toBe(true)
    expect(text.value).toBe('')
  })

  it('aborts capture and drops late results when the composer scope ends', () => {
    const scope = effectScope()
    const text = ref('')
    scope.run(() => useComposerVoice(text).toggleVoiceInput())
    const rec = FakeRecognition.last!
    scope.stop()
    expect(rec.abort).toHaveBeenCalledTimes(1)
    rec.onresult!({ results: [[{ transcript: 'late' }]] })
    expect(text.value).toBe('')
  })

  it('without the Web Speech API it still asks for the microphone, then says it is unsupported', async () => {
    delete win.SpeechRecognition
    const stop = vi.fn()
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] })
    Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true })
    const { isVoiceRecording, toggleVoiceInput } = useComposerVoice(ref(''))
    toggleVoiceInput()
    await vi.waitFor(() => expect(showToast).toHaveBeenCalledWith('chat.input.voiceUnsupported', 'warning'))
    expect(getUserMedia).toHaveBeenCalledWith({ audio: true })
    expect(stop).toHaveBeenCalled()
    expect(isVoiceRecording.value).toBe(false)
  })
})
