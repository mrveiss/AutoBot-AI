// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #22349: a stand-in for the `useVoiceConversation` return value, so the voice panel, the overlay and the shared
// view composable are tested against the surface they read without starting any transport or microphone.
import { ref, type Ref } from 'vue'
import { vi } from 'vitest'
import type { ConversationMode, ConversationState } from '@/composables/useVoiceConversation'

export interface VoiceFake {
  state: Ref<ConversationState>
  mode: Ref<ConversationMode>
  wsConnected: Ref<boolean>
  realtimeConnectionState: Ref<string>
  currentTranscript: Ref<string>
  currentLanguage: Ref<string>
  bubbles: Ref<{ id: string; sender: 'user' | 'assistant'; content: string }[]>
  isActive: Ref<boolean>
  errorMessage: Ref<string | null>
  audioLevel: Ref<number>
  silenceThreshold: Ref<number>
  micAccessAvailable: Ref<boolean>
  stateLabel: Ref<string>
  toggleListening: ReturnType<typeof vi.fn>
  setMode: ReturnType<typeof vi.fn>
  deactivate: ReturnType<typeof vi.fn>
  cleanup: ReturnType<typeof vi.fn>
}

export function createVoiceFake(): VoiceFake {
  return {
    state: ref<ConversationState>('idle'),
    mode: ref<ConversationMode>('walkie-talkie'),
    wsConnected: ref(false),
    realtimeConnectionState: ref('disconnected'),
    currentTranscript: ref(''),
    currentLanguage: ref('en'),
    bubbles: ref([]),
    isActive: ref(true),
    errorMessage: ref<string | null>(null),
    audioLevel: ref(0),
    silenceThreshold: ref(800),
    micAccessAvailable: ref(true),
    stateLabel: ref('Idle'),
    toggleListening: vi.fn(),
    setMode: vi.fn(),
    deactivate: vi.fn(),
    cleanup: vi.fn(),
  }
}
