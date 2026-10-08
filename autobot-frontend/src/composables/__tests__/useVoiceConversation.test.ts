// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// useVoiceConversation watcher single-registration (#12153): this composable
// is a MODULE-SINGLETON (state declared at module scope, #1037) but is
// invoked once per mounted caller (VoiceConversationPanel,
// VoiceConversationOverlay, ChatInterface). Registering `watch(isSpeaking,
// ...)` / `watch(prefLanguage, ...)` inside the exported function body meant
// every mounted caller registered ANOTHER watcher on the same module-level
// refs, so a single TTS-completion or language-preference change fired
// `_resumeAutoListening` (and the language handler) once PER mounted
// caller. The fix hoists both watch() registrations to module scope
// (immediately after `_handleVadSpeechEnd`, before `useVoiceConversation()`)
// so they run exactly once, no matter how many times the composable is
// called.
//
// isSpeaking/language are themselves module-singleton refs (see
// useVoiceOutput.ts / usePreferences.ts) — the mocks below replicate that by
// creating each ref ONCE inside the mock factory closure, so every call to
// useVoiceOutput()/usePreferences() (production or test) observes the same
// instance, exactly like the real composables.

import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'

vi.mock('@/composables/useVoiceOutput', () => {
  const isSpeaking = ref(false)
  return {
    useVoiceOutput: () => ({
      isSpeaking,
      wsConnected: ref(false),
      unlockAudio: vi.fn(),
      stopSpeaking: vi.fn(),
      speakStreaming: vi.fn(),
      flushStreaming: vi.fn(),
      subscribeVoiceMessages: vi.fn(() => vi.fn()),
      sendVoiceFrame: vi.fn(),
    }),
  }
})

vi.mock('@/composables/usePreferences', () => {
  const language = ref('en')
  return {
    usePreferences: () => ({ language }),
  }
})

vi.mock('@/composables/useVoiceProfiles', () => ({
  useVoiceProfiles: () => ({ effectiveVoiceId: ref('') }),
}))

vi.mock('@/composables/useRealtimeVoice', () => ({
  useRealtimeVoice: () => ({
    connectionState: ref('idle'),
    errorMessage: ref(''),
    disconnectReason: ref(''),
    connect: vi.fn(),
    disconnect: vi.fn(),
  }),
}))

vi.mock('@/models/controllers', () => ({
  useChatController: () => ({ sendMessage: vi.fn().mockResolvedValue(undefined) }),
}))

vi.mock('@/stores/useChatStore', () => ({
  useChatStore: () => ({ sessions: [], currentSessionId: null }),
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
}))

vi.mock('@/utils/fetchWithAuth', () => ({
  fetchWithAuth: vi.fn(),
}))

// createLogger is called ONCE by production (module scope, `const logger =
// createLogger(...)`); the `debug` fn is defined inside this factory's
// closure (not the returned arrow fn) so every createLogger() call — in
// production or in the test below — shares the SAME spy instance.
vi.mock('@/utils/debugUtils', () => {
  const debug = vi.fn()
  return {
    createLogger: () => ({ debug, warn: vi.fn(), error: vi.fn() }),
  }
})

import {
  useVoiceConversation,
  DEFAULT_SILENCE_THRESHOLD_MS,
  _silenceMsToRedemptionMs,
  _silenceMsToOffsetFrames,
} from '../useVoiceConversation'
import { useVoiceOutput } from '@/composables/useVoiceOutput'
import { usePreferences } from '@/composables/usePreferences'
import { createLogger } from '@/utils/debugUtils'
import { _sanitizeForSpeech } from '../useVoiceConversation'

// Same singleton instances the module-scope watch() calls in
// useVoiceConversation.ts observe.
const { isSpeaking: mockIsSpeaking } = useVoiceOutput()
const { language: mockLanguage } = usePreferences()
const { debug: debugSpy } = createLogger('test')

describe('useVoiceConversation — watcher single-registration (#12153)', () => {
  it('fires the language-change watcher exactly once per preference change, regardless of how many callers are mounted', async () => {
    // Simulate 3 mounted callers (VoiceConversationPanel,
    // VoiceConversationOverlay, ChatInterface) all invoking the composable.
    // Pre-fix, each call registered its OWN `watch(prefLanguage, ...)` on
    // this same module-singleton ref, so a single language change would
    // have logged 3 times instead of 1.
    useVoiceConversation()
    useVoiceConversation()
    useVoiceConversation()

    debugSpy.mockClear()
    mockLanguage.value = 'de'
    await nextTick()

    const langChangeCalls = debugSpy.mock.calls.filter(
      (args) => args[0] === 'Language preference changed:',
    )
    expect(langChangeCalls).toHaveLength(1)
    expect(langChangeCalls[0][1]).toBe('de')

    mockLanguage.value = 'en' // reset for isolation from other tests
    await nextTick()
    debugSpy.mockClear()
  })

  it('single-caller trace: isSpeaking flip still resumes listening exactly as before the hoist', async () => {
    // With a single mounted caller, behavior must be identical to pre-fix:
    // TTS completion (isSpeaking true→false) while state === 'speaking' in
    // full-duplex mode resumes listening via _resumeAutoListening.
    const conversation = useVoiceConversation()
    conversation.mode.value = 'full-duplex'
    conversation.isActive.value = true
    conversation.state.value = 'speaking'
    conversation.errorMessage.value = ''

    mockIsSpeaking.value = true
    await nextTick()
    mockIsSpeaking.value = false
    await nextTick()

    // _resumeAutoListening → _startListeningInternal; jsdom has no
    // SpeechRecognition, so the browser-unsupported error surfaces and
    // state settles at 'idle' — same as pre-fix single-caller behavior.
    expect(conversation.state.value).toBe('idle')
    expect(conversation.errorMessage.value).toContain('Chrome, Edge, or Safari 15+')

    conversation.isActive.value = false
  })
})

describe('useVoiceConversation — endpointing single-knob wiring (#12505)', () => {
  it('defaults the silence-tolerance knob to a conversational value, not the old ~250ms cutoff', () => {
    // The bug was a 250ms Silero redemption / ~21ms worklet window that
    // finalized on a natural sub-second pause. The single knob must default
    // well above that (≥ ~500ms) so a conversational half-second pause is
    // tolerated.
    expect(DEFAULT_SILENCE_THRESHOLD_MS).toBe(800)
    expect(DEFAULT_SILENCE_THRESHOLD_MS).toBeGreaterThanOrEqual(500)
    // The default the composable actually exposes matches the constant.
    const conversation = useVoiceConversation()
    expect(conversation.silenceThreshold.value).toBe(DEFAULT_SILENCE_THRESHOLD_MS)
  })

  it('wires the knob into Silero redemptionMs — the endpointer is no longer dead config', () => {
    // Identity within the slider range: the knob IS the redemption window.
    expect(_silenceMsToRedemptionMs(DEFAULT_SILENCE_THRESHOLD_MS)).toBe(800)
    expect(_silenceMsToRedemptionMs(1500)).toBe(1500)
    // Clamped to the supported UI slider range (500-3000ms).
    expect(_silenceMsToRedemptionMs(100)).toBe(500)
    expect(_silenceMsToRedemptionMs(9999)).toBe(3000)
    // Crucially, it is NEVER the old too-short 250ms cutoff.
    expect(_silenceMsToRedemptionMs(DEFAULT_SILENCE_THRESHOLD_MS)).toBeGreaterThan(250)
  })

  it('wires the knob into the AudioWorklet silence window (OFFSET_FRAMES), matching redemption tolerance', () => {
    // frames = round(ms / (128/sampleRate*1000)). At 48kHz a render quantum
    // is 128/48000*1000 ≈ 2.667ms, so 800ms ≈ 300 frames — vastly longer
    // than the old hardcoded 8 frames (~21ms).
    const frames48k = _silenceMsToOffsetFrames(DEFAULT_SILENCE_THRESHOLD_MS, 48000)
    expect(frames48k).toBe(300)
    expect(frames48k).toBeGreaterThan(8)
    // At 16kHz the render quantum is 8ms, so 800ms = 100 frames.
    expect(_silenceMsToOffsetFrames(DEFAULT_SILENCE_THRESHOLD_MS, 16000)).toBe(100)
    // Never collapses below one frame even for tiny values.
    expect(_silenceMsToOffsetFrames(1, 48000)).toBeGreaterThanOrEqual(1)
  })
})

describe('_sanitizeForSpeech removes markup by parsing, not matching (#18065)', () => {
  // Drives the PRODUCTION function. The first version of these tests re-implemented
  // the parser locally, so they would have passed even if `_sanitizeForSpeech`
  // reverted to regex removal or stopped removing scripts — the defect they exist
  // to prevent. `shapeForSpeech` runs after the sanitiser, so assertions below
  // check for ABSENCE of markup and presence of words rather than exact equality.
  const spoken = (t: string): string => _sanitizeForSpeech(t)

  it('keeps prose containing comparison operators', () => {
    // The regex form turned this into 'math: a  d' — it ate everything between
    // `<` and the next `>`. Any sentence with a comparison was damaged before TTS.
    const out = spoken('math: a < b and c > d')
    expect(out).toContain('b')
    expect(out).toContain('d')
  })

  it.each([
    ['<textarea><script>secret</script></textarea>', 'secret'],
    ['<xmp><script>y</script></xmp>', 'y'],
    ['<iframe><script>z</script></iframe>', 'z'],
  ])('never speaks the contents of a raw-text container: %s', (input, leaked) => {
    // These parse their contents as TEXT, so there is no script ELEMENT to remove
    // and `textContent` handed the literal `<script>…</script>` to the voice.
    const out = spoken(input)
    expect(out).not.toMatch(/<script/i)
    expect(out).not.toContain(leaked)
  })

  it('drops a script body even when the end tag carries whitespace or attributes', () => {
    // `</script\t\n bar>` is a VALID end tag that `<\/script\s*>` missed, so the
    // body survived and was spoken.
    expect(spoken('tricky <script>xyzzy</script\t\n bar> tail')).not.toContain('xyzzy')
  })

  it.each([
    ['<style>body{color:red}</style>styled', 'color:red'],
    ['<!-- a comment > still --> after', 'still'],
    ['<div title="a>b">attr with gt</div>', 'b">'],
  ])('never speaks leftovers from %s', (input, leaked) => {
    expect(spoken(input)).not.toContain(leaked)
  })

  it('still removes a well-formed script and its body', () => {
    const out = spoken('Hello <script>alert(1)</script> world')
    expect(out).not.toContain('alert')
    expect(out).toContain('Hello')
  })

  it('CONTROL: leaves text with no markup alone', () => {
    // Without this, a sanitiser that returned '' would satisfy every assertion above.
    expect(spoken('plain spoken words')).toContain('plain spoken words')
  })
})
