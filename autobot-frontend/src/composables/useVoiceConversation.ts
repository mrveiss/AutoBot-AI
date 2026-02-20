/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useVoiceConversation.ts - Voice conversation state machine (#1029)
 * Manages walkie-talkie, hands-free, and full-duplex voice conversation modes.
 * Tier 1 (walkie-talkie) uses browser SpeechRecognition + existing TTS.
 */

import { ref, computed, watch } from 'vue'
import type { ChatMessage } from '@/stores/useChatStore'
import { useVoiceOutput } from '@/composables/useVoiceOutput'
import { useChatController } from '@/models/controllers'
import { useChatStore } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useVoiceConversation')

export type ConversationMode = 'walkie-talkie' | 'hands-free' | 'full-duplex'
export type ConversationState =
  | 'idle'
  | 'listening'
  | 'processing'
  | 'speaking'

export interface VoiceBubble {
  id: string
  sender: 'user' | 'assistant'
  content: string
  timestamp: number
}

// Module-level singletons — shared across all component instances (#1037)
const state = ref<ConversationState>('idle')
const mode = ref<ConversationMode>('walkie-talkie')
const currentTranscript = ref('')
const bubbles = ref<VoiceBubble[]>([])
const isActive = ref(false)
const errorMessage = ref('')

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _recognition: any = null
// Response message types that should be spoken (skip thoughts/planning/debug)
const _SPEAKABLE_TYPES = new Set(['response', 'message'])

function _generateId(): string {
  return `vb_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

export function useVoiceConversation() {
  const store = useChatStore()
  const controller = useChatController()
  const { speak, isSpeaking } = useVoiceOutput()

  const isListening = computed(() => state.value === 'listening')
  const isProcessing = computed(() => state.value === 'processing')

  const stateLabel = computed(() => {
    switch (state.value) {
      case 'idle': return 'Tap to speak'
      case 'listening': return 'Listening...'
      case 'processing': return 'Processing...'
      case 'speaking': return 'AutoBot is speaking...'
      default: return ''
    }
  })

  function activate(): void {
    isActive.value = true
    state.value = 'idle'
    bubbles.value = []
    errorMessage.value = ''
    logger.debug('Voice conversation activated')
  }

  function deactivate(): void {
    _stopRecognition()
    isActive.value = false
    state.value = 'idle'
    currentTranscript.value = ''
    logger.debug('Voice conversation deactivated')
  }

  function startListening(): void {
    if (state.value !== 'idle') return
    errorMessage.value = ''

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const w = window as any
    const SpeechRecognitionCtor =
      w.SpeechRecognition ?? w.webkitSpeechRecognition

    if (!SpeechRecognitionCtor) {
      errorMessage.value =
        'Voice input requires Chrome, Edge, or Safari 15+.'
      return
    }

    _recognition = new SpeechRecognitionCtor()
    _recognition.continuous = false
    _recognition.interimResults = true
    _recognition.lang = 'en-US'

    _recognition.onstart = () => {
      state.value = 'listening'
      currentTranscript.value = ''
      logger.debug('Voice recognition started')
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    _recognition.onresult = (event: any) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const transcript = Array.from(event.results as any[])
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .map((r: any) => r[0].transcript as string)
        .join('')
      currentTranscript.value = transcript
    }

    _recognition.onend = () => {
      // Auto-send when recognition ends (user stopped speaking)
      const text = currentTranscript.value.trim()
      if (text) {
        _sendTranscript(text)
      } else {
        state.value = 'idle'
      }
      _recognition = null
    }

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    _recognition.onerror = (event: any) => {
      logger.error('Voice recognition error:', event.error)
      _recognition = null
      if (event.error === 'not-allowed') {
        errorMessage.value =
          'Microphone access denied. Allow mic in browser settings.'
      } else if (event.error !== 'aborted') {
        errorMessage.value = `Speech error: ${event.error}`
      }
      state.value = 'idle'
    }

    _recognition.start()
  }

  function stopListening(): void {
    if (_recognition) {
      _recognition.stop()
      // onend handler will fire and call _sendTranscript
    }
  }

  function toggleListening(): void {
    if (state.value === 'listening') {
      stopListening()
    } else if (state.value === 'idle') {
      startListening()
    }
  }

  async function _sendTranscript(text: string): Promise<void> {
    state.value = 'processing'

    bubbles.value.push({
      id: _generateId(),
      sender: 'user',
      content: text,
      timestamp: Date.now(),
    })

    try {
      await controller.sendMessage(text, { use_knowledge: false })

      // Streaming complete — find the last assistant response
      const response = _getLastAssistantContent()
      if (response && isActive.value) {
        bubbles.value.push({
          id: _generateId(),
          sender: 'assistant',
          content: response,
          timestamp: Date.now(),
        })

        state.value = 'speaking'
        await speak(response, true)

        // If speak() failed (e.g. TTS 403), isSpeaking never
        // became true so the watcher won't recover — do it here.
        if (!isSpeaking.value && state.value === 'speaking') {
          state.value = 'idle'
          logger.debug('TTS did not start, recovering to idle')
        }
      } else {
        state.value = 'idle'
      }
    } catch (err) {
      logger.error('Failed to send voice transcript:', err)
      errorMessage.value = 'Failed to send message. Try again.'
      state.value = 'idle'
    }
  }

  function _getLastAssistantContent(): string | null {
    const session = store.sessions.find(
      (s) => s.id === store.currentSessionId,
    )
    const msgs: ChatMessage[] = session?.messages ?? []
    for (let i = msgs.length - 1; i >= 0; i--) {
      const msg = msgs[i]
      if (msg.sender !== 'assistant' || !msg.content) continue
      // Skip thought/planning/debug — only speak actual responses
      if (msg.type && !_SPEAKABLE_TYPES.has(msg.type)) continue
      return msg.content
    }
    return null
  }

  // Watch isSpeaking to transition back to idle when TTS finishes
  watch(isSpeaking, (speaking) => {
    if (!speaking && state.value === 'speaking') {
      state.value = 'idle'
      logger.debug('TTS finished, returning to idle')
    }
  })

  function cleanup(): void {
    deactivate()
  }

  function _stopRecognition(): void {
    if (_recognition) {
      try {
        _recognition.abort()
      } catch {
        // ignore
      }
      _recognition = null
    }
    currentTranscript.value = ''
  }

  return {
    // State
    state,
    mode,
    currentTranscript,
    bubbles,
    isActive,
    errorMessage,

    // Computed
    isListening,
    isProcessing,
    stateLabel,

    // Actions
    activate,
    deactivate,
    startListening,
    stopListening,
    toggleListening,
    cleanup,
  }
}
