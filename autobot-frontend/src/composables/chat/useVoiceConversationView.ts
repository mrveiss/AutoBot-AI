// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0

/**
 * The presentational state the voice panel and the voice overlay share (#22349): the mic and state icons, the mic
 * hint, whether the mode listens by itself, the insecure-context flag and the connection indicator. It reads the
 * `useVoiceConversation` return value it is given and changes nothing in it, so the two placements of the voice UI
 * cannot drift apart on this logic.
 */
import { computed, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import type { IconName } from '@/components/ui/Icon.vue'
import type { ConversationState, useVoiceConversation } from '@/composables/useVoiceConversation'

type VoiceConversation = ReturnType<typeof useVoiceConversation>

/** The two hints the placements word differently (full i18n keys); the other hints are shared. */
export interface VoiceHintKeys {
  /** Listening in an auto mode: the panel is brief, the overlay is a sentence. */
  autoListening: string
  /** Processing outside hands-free. */
  processing: string
}

/** Every voice hint as a full key, so a key scan finds each one (no `chat.voice.${...}` lookups). */
export const VOICE_HINT_KEYS = {
  panel: { autoListening: 'chat.voice.hintAutoDetects', processing: 'chat.voice.hintProcessing' },
  overlay: { autoListening: 'chat.voice.hintAutoListening', processing: 'chat.voice.hintWaitingResponse' },
} as const satisfies Record<string, VoiceHintKeys>

const SHARED_HINTS = {
  tapToStop: 'chat.voice.hintTapToStop',
  transcribing: 'chat.voice.hintTranscribing',
  interrupt: 'chat.voice.hintInterrupt',
  autoStart: 'chat.voice.hintAutoStart',
  tapToSpeak: 'chat.voice.hintTapToSpeak',
} as const

export interface VoiceConnection {
  connected: boolean
}

export function stateIconFor(state: ConversationState): IconName {
  switch (state) {
    case 'listening': return 'microphone'
    case 'processing': return 'spinner'
    case 'speaking': return 'volume-up'
    default: return 'microphone-slash'
  }
}

export function micIconFor(state: ConversationState, isAutoMode: boolean): IconName {
  switch (state) {
    case 'listening': return isAutoMode ? 'microphone' : 'stop'
    case 'processing': return 'spinner'
    case 'speaking': return 'stop'
    default: return 'microphone'
  }
}

/** The i18n key of the mic hint for a state; the caller translates it. */
export function micHintFor(state: ConversationState, isAutoMode: boolean, isHandsFree: boolean, keys: VoiceHintKeys): string {
  switch (state) {
    case 'listening': return isAutoMode ? keys.autoListening : SHARED_HINTS.tapToStop
    case 'processing': return isHandsFree ? SHARED_HINTS.transcribing : keys.processing
    case 'speaking': return SHARED_HINTS.interrupt
    default: return isAutoMode ? SHARED_HINTS.autoStart : SHARED_HINTS.tapToSpeak
  }
}

export function useVoiceConversationView(voice: VoiceConversation, hintKeys: VoiceHintKeys) {
  const { t } = useI18n()

  const isHandsFree = computed(() => voice.mode.value === 'hands-free')
  // Modes that listen without a tap: they need the microphone from the moment they start.
  const isAutoMode = computed(() => ['full-duplex', 'hands-free', 'realtime-webrtc'].includes(voice.mode.value))
  // A mic-dependent mode is selected but the browser cannot provide getUserMedia (#1059).
  const showInsecureContextWarning = computed(() => isAutoMode.value && !voice.micAccessAvailable.value)

  const stateIcon = computed(() => stateIconFor(voice.state.value))
  const micIcon = computed(() => micIconFor(voice.state.value, isAutoMode.value))
  const micHint = computed(() => t(micHintFor(voice.state.value, isAutoMode.value, isHandsFree.value, hintKeys)))

  // The dot is shown for the two transports that have a connection to report.
  const connection: ComputedRef<VoiceConnection | null> = computed(() => {
    if (voice.mode.value === 'full-duplex') return { connected: !!voice.wsConnected?.value }
    if (voice.mode.value === 'realtime-webrtc') return { connected: voice.realtimeConnectionState.value === 'connected' }
    return null
  })

  return { isAutoMode, isHandsFree, showInsecureContextWarning, stateIcon, micIcon, micHint, connection }
}
