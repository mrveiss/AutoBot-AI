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
import { ref } from 'vue'

const showToast = vi.hoisted(() => vi.fn())
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (k: string) => k }) }))
vi.mock('@autobot/ui', () => ({ useToast: () => ({ showToast }) }))

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
    expect(isVoiceRecording.value).toBe(false)
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
