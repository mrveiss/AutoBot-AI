// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * One-message voice dictation for the composer (Web Speech API), moved out of ChatInput.vue
 * (#18243). The transcript replaces the draft while it is recorded. Where the browser has no
 * recogniser it still asks for the microphone, so the person sees the permission prompt rather
 * than a silent failure. Voice conversation is a separate stack (`useVoiceConversation`).
 */
import { ref, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useComposerVoice')

// Minimal Web Speech API shapes (not in TS lib.dom): only the fields this module reads.
interface SpeechResultEvent { results: SpeechRecognitionResultList }
interface SpeechErrorEvent { error: string }
interface Recognition {
  continuous: boolean
  interimResults: boolean
  lang: string
  onstart: (() => void) | null
  onresult: ((event: SpeechResultEvent) => void) | null
  onend: (() => void) | null
  onerror: ((event: SpeechErrorEvent) => void) | null
  start: () => void
  stop: () => void
}
type RecognitionCtor = new () => Recognition

const RECOGNITION_LANG = 'en-US'

function recognitionCtor(): RecognitionCtor | undefined {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

export function useComposerVoice(messageText: Ref<string>) {
  const { t } = useI18n()
  const { showToast } = useToast()
  const isVoiceRecording = ref(false)
  let recognition: Recognition | null = null // internal, not reactive

  /** No Web Speech API: still trigger the mic permission prompt, then say it is unsupported. */
  async function explainUnsupported(): Promise<void> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((track: MediaStreamTrack) => track.stop())
    } catch (err) {
      logger.error('Microphone access denied:', err)
    }
    showToast(t('chat.input.voiceUnsupported'), 'warning')
  }

  const transcriptOf = (event: SpeechResultEvent): string =>
    Array.from(event.results as unknown as SpeechRecognitionResult[]).map((r) => r[0].transcript as string).join('')

  function bindHandlers(rec: Recognition): void {
    rec.onstart = () => {
      isVoiceRecording.value = true
      logger.debug('Voice recognition started')
    }
    rec.onresult = (event) => { messageText.value = transcriptOf(event) }
    rec.onend = () => {
      isVoiceRecording.value = false
      recognition = null
      logger.debug('Voice recognition ended')
    }
    rec.onerror = (event) => {
      logger.error('Voice recognition error:', event.error)
      isVoiceRecording.value = false
      recognition = null
      if (event.error === 'not-allowed') showToast(t('chat.input.micDenied'), 'error')
    }
  }

  async function startVoiceRecording(): Promise<void> {
    const Ctor = recognitionCtor()
    if (!Ctor) return explainUnsupported()
    recognition = new Ctor()
    recognition.continuous = false
    recognition.interimResults = true
    recognition.lang = RECOGNITION_LANG
    bindHandlers(recognition)
    recognition.start()
  }

  function stopVoiceRecording(): void {
    recognition?.stop()
    isVoiceRecording.value = false
    logger.debug('Voice recording stopped')
  }

  const toggleVoiceInput = (): void => {
    if (isVoiceRecording.value) stopVoiceRecording()
    else void startVoiceRecording()
  }

  return { isVoiceRecording, toggleVoiceInput }
}
