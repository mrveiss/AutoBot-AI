/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useVoiceOutput.ts - TTS voice output composable (#928)
 * Manages voice output toggle state and plays synthesized audio via Kani-TTS-2.
 */

import { ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useVoiceOutput')

const STORAGE_KEY = 'autobot-voice-output-enabled'

// Module-level singletons so state is shared across component instances
const voiceOutputEnabled = ref<boolean>(
  localStorage.getItem(STORAGE_KEY) === 'true'
)
const isSpeaking = ref<boolean>(false)

let _currentAudio: HTMLAudioElement | null = null

function _stopCurrentAudio(): void {
  if (_currentAudio) {
    _currentAudio.pause()
    _currentAudio.src = ''
    _currentAudio = null
  }
  isSpeaking.value = false
}

function _playAudioBlob(blob: Blob): void {
  _stopCurrentAudio()
  const url = URL.createObjectURL(blob)
  const audio = new Audio(url)
  _currentAudio = audio
  isSpeaking.value = true
  audio.onended = () => {
    URL.revokeObjectURL(url)
    isSpeaking.value = false
    _currentAudio = null
  }
  audio.onerror = (e) => {
    logger.error('Audio playback error:', e)
    URL.revokeObjectURL(url)
    isSpeaking.value = false
    _currentAudio = null
  }
  audio.play().catch((e) => {
    logger.error('Audio play() rejected:', e)
    isSpeaking.value = false
  })
}

export function useVoiceOutput() {
  function toggleVoiceOutput(): void {
    voiceOutputEnabled.value = !voiceOutputEnabled.value
    localStorage.setItem(STORAGE_KEY, String(voiceOutputEnabled.value))
    logger.debug('Voice output toggled:', voiceOutputEnabled.value)
    if (!voiceOutputEnabled.value) {
      _stopCurrentAudio()
    }
  }

  async function speak(text: string): Promise<void> {
    if (!voiceOutputEnabled.value || !text.trim()) return
    if (isSpeaking.value) _stopCurrentAudio()

    try {
      const formData = new FormData()
      formData.append('text', text)
      const response = await fetch('/api/voice/synthesize', {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        logger.warn('TTS synthesize failed:', response.status)
        return
      }
      const blob = await response.blob()
      _playAudioBlob(blob)
    } catch (e) {
      logger.error('speak() error:', e)
    }
  }

  return {
    voiceOutputEnabled,
    isSpeaking,
    toggleVoiceOutput,
    speak,
  }
}
