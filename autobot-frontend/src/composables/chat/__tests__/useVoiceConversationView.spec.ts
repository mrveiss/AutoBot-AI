// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: the presentational state the voice panel and the voice overlay share -- mic icon and hint per state and
// mode, the auto-mode and insecure-context flags, the state icon and the connection indicator.
import { describe, it, expect, vi } from 'vitest'
import { createVoiceFake } from '@/components/chat/__tests__/voiceConversationFake'

vi.mock('vue-i18n', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-i18n')>()),
  useI18n: () => ({ t: (k: string) => k, locale: { value: 'en' } }),
}))

import { useVoiceConversationView, VOICE_HINT_KEYS } from '../useVoiceConversationView'
import type { ConversationMode, ConversationState } from '@/composables/useVoiceConversation'

const PANEL = VOICE_HINT_KEYS.panel
const OVERLAY = VOICE_HINT_KEYS.overlay

function viewFor(state: ConversationState, mode: ConversationMode, keys = PANEL) {
  const voice = createVoiceFake()
  voice.state.value = state
  voice.mode.value = mode
  return { voice, view: useVoiceConversationView(voice as never, keys) }
}

describe('useVoiceConversationView (#22349)', () => {
  it.each([
    ['idle', 'walkie-talkie', 'microphone', 'chat.voice.hintTapToSpeak'],
    ['idle', 'hands-free', 'microphone', 'chat.voice.hintAutoStart'],
    ['listening', 'walkie-talkie', 'stop', 'chat.voice.hintTapToStop'],
    ['listening', 'full-duplex', 'microphone', 'chat.voice.hintAutoDetects'],
    ['processing', 'walkie-talkie', 'spinner', 'chat.voice.hintProcessing'],
    ['processing', 'hands-free', 'spinner', 'chat.voice.hintTranscribing'],
    ['speaking', 'realtime-webrtc', 'stop', 'chat.voice.hintInterrupt'],
  ] as const)('%s in %s: mic icon %s, hint %s', (state, mode, icon, hint) => {
    const { view } = viewFor(state, mode)
    expect(view.micIcon.value).toBe(icon)
    expect(view.micHint.value).toBe(hint)
  })

  it('words the two placement-specific hints from the keys it is given', () => {
    expect(viewFor('listening', 'hands-free', OVERLAY).view.micHint.value).toBe('chat.voice.hintAutoListening')
    expect(viewFor('processing', 'full-duplex', OVERLAY).view.micHint.value).toBe('chat.voice.hintWaitingResponse')
  })

  it.each([
    ['idle', 'microphone-slash'],
    ['listening', 'microphone'],
    ['processing', 'spinner'],
    ['speaking', 'volume-up'],
  ] as const)('state icon for %s is %s', (state, icon) => {
    expect(viewFor(state, 'walkie-talkie').view.stateIcon.value).toBe(icon)
  })

  it('flags the insecure context only for a microphone-dependent mode without microphone access', () => {
    const { voice, view } = viewFor('idle', 'walkie-talkie')
    voice.micAccessAvailable.value = false
    expect(view.showInsecureContextWarning.value).toBe(false)
    voice.mode.value = 'hands-free'
    expect(view.showInsecureContextWarning.value).toBe(true)
    voice.micAccessAvailable.value = true
    expect(view.showInsecureContextWarning.value).toBe(false)
  })

  it('reports the connection only for full-duplex and realtime, from each one\'s own state', () => {
    const { voice, view } = viewFor('idle', 'walkie-talkie')
    expect(view.connection.value).toBeNull()
    voice.mode.value = 'full-duplex'
    expect(view.connection.value).toEqual({ connected: false })
    voice.wsConnected.value = true
    expect(view.connection.value).toEqual({ connected: true })
    voice.mode.value = 'realtime-webrtc'
    expect(view.connection.value).toEqual({ connected: false })
    voice.realtimeConnectionState.value = 'connected'
    expect(view.connection.value).toEqual({ connected: true })
  })

  it('only hands-free reports isHandsFree', () => {
    expect(viewFor('idle', 'hands-free').view.isHandsFree.value).toBe(true)
    expect(viewFor('idle', 'full-duplex').view.isHandsFree.value).toBe(false)
  })
})
