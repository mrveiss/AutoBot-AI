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
import { getCurrentScope, onScopeDispose, ref, type Ref } from 'vue'
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
  abort: () => void
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
  let stopping = false // stop() was asked for and onend has not come yet

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

  /** Handlers act only for the recogniser that is current: a late callback of an older one is dropped. */
  function bindHandlers(rec: Recognition): void {
    const current = (): boolean => recognition === rec
    rec.onstart = () => {
      if (!current()) return
      isVoiceRecording.value = true
      logger.debug('Voice recognition started')
    }
    rec.onresult = (event) => { if (current()) messageText.value = transcriptOf(event) }
    rec.onend = () => {
      if (!current()) return
      isVoiceRecording.value = false
      recognition = null
      stopping = false
      logger.debug('Voice recognition ended')
    }
    rec.onerror = (event) => {
      if (!current()) return
      logger.error('Voice recognition error:', event.error)
      isVoiceRecording.value = false
      recognition = null
      stopping = false
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
    try {
      recognition.start()
    } catch (err) {
      // a throwing start() must not leave a dead recogniser behind: the next toggle has to start again
      logger.error('Voice recognition failed to start:', err)
      recognition = null
      isVoiceRecording.value = false
      showToast(t('chat.input.micDenied'), 'error')
    }
  }

  /** A second press while stopping: abort() ends the recogniser for good (its late callbacks are then dropped). */
  function abortStopping(): void {
    const rec = recognition
    recognition = null
    stopping = false
    isVoiceRecording.value = false
    rec?.abort()
  }

  function stopVoiceRecording(): void {
    // The flag stays up until onend: stop() can still deliver a final transcript, so a send in the gap would race it.
    recognition?.stop()
    stopping = true
    logger.debug('Voice recording stopped')
  }

  // A recogniser exists from start() until its onend, which is wider than `isVoiceRecording`
  // (false before onstart): a toggle in that gap stops, it never starts a second one; a toggle after stop() aborts.
  const toggleVoiceInput = (): void => {
    if (stopping) abortStopping() // the recogniser did not end after stop(): give the composer back
    else if (isVoiceRecording.value || recognition) stopVoiceRecording()
    else void startVoiceRecording()
  }

  // Leaving the composer ends capture; abort() (not stop()) so no final result is delivered afterwards.
  if (getCurrentScope()) {
    onScopeDispose(() => {
      const rec = recognition
      recognition = null
      stopping = false
      rec?.abort()
      isVoiceRecording.value = false
    })
  }

  return { isVoiceRecording, toggleVoiceInput }
}
