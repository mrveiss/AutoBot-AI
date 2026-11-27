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
import type { useVoiceConversation } from '@/composables/useVoiceConversation'

type VoiceConversation = ReturnType<typeof useVoiceConversation>

/** The two hints the placements word differently; the other hints are shared. */
export interface VoiceHintKeys {
  /** Listening in an auto mode: the panel is brief, the overlay is a sentence. */
  autoListening: string
  /** Processing outside hands-free. */
  processing: string
}

export interface VoiceConnection {
  connected: boolean
}

export function useVoiceConversationView(voice: VoiceConversation, hintKeys: VoiceHintKeys) {
  const { t } = useI18n()

  const isHandsFree = computed(() => voice.mode.value === 'hands-free')
  // Modes that listen without a tap: they need the microphone from the moment they start.
  const isAutoMode = computed(() => ['full-duplex', 'hands-free', 'realtime-webrtc'].includes(voice.mode.value))
  // A mic-dependent mode is selected but the browser cannot provide getUserMedia (#1059).
  const showInsecureContextWarning = computed(() => isAutoMode.value && !voice.micAccessAvailable.value)

  const stateIcon = computed<IconName>(() => {
    switch (voice.state.value) {
      case 'listening': return 'microphone'
      case 'processing': return 'spinner'
      case 'speaking': return 'volume-up'
      default: return 'microphone-slash'
    }
  })

  const micIcon = computed<IconName>(() => {
    switch (voice.state.value) {
      case 'listening': return isAutoMode.value ? 'microphone' : 'stop'
      case 'processing': return 'spinner'
      case 'speaking': return 'stop'
      default: return 'microphone'
    }
  })

  const micHint = computed(() => {
    switch (voice.state.value) {
      case 'listening':
        return isAutoMode.value ? t(`chat.voice.${hintKeys.autoListening}`) : t('chat.voice.hintTapToStop')
      case 'processing':
        return isHandsFree.value ? t('chat.voice.hintTranscribing') : t(`chat.voice.${hintKeys.processing}`)
      case 'speaking':
        return t('chat.voice.hintInterrupt')
      default:
        return isAutoMode.value ? t('chat.voice.hintAutoStart') : t('chat.voice.hintTapToSpeak')
    }
  })

  // The dot is shown for the two transports that have a connection to report.
  const connection: ComputedRef<VoiceConnection | null> = computed(() => {
    if (voice.mode.value === 'full-duplex') return { connected: !!voice.wsConnected?.value }
    if (voice.mode.value === 'realtime-webrtc') return { connected: voice.realtimeConnectionState.value === 'connected' }
    return null
  })

  return { isAutoMode, isHandsFree, showInsecureContextWarning, stateIcon, micIcon, micHint, connection }
}
