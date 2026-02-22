/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useVoiceOutput.ts - TTS voice output composable (#928, #1031)
 * Manages voice output toggle state and plays synthesized audio via Pocket TTS.
 * Supports both single-shot speak() and streaming playAudioChunk() for full-duplex.
 */

import { ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'
import { useVoiceProfiles } from '@/composables/useVoiceProfiles'

const logger = createLogger('useVoiceOutput')

const STORAGE_KEY = 'autobot-voice-output-enabled'

// Module-level singletons so state is shared across component instances
const voiceOutputEnabled = ref<boolean>(
  localStorage.getItem(STORAGE_KEY) === 'true'
)
const isSpeaking = ref<boolean>(false)

// AudioContext survives expired user gestures — once resumed, it stays unlocked.
// new Audio().play() requires a fresh gesture each time and fails after delay.
let _audioContext: AudioContext | null = null
let _currentSource: AudioBufferSourceNode | null = null

// Queue for streaming audio chunks (#1031)
let _chunkQueue: ArrayBuffer[] = []
let _isPlayingChunks = false

function _getOrCreateContext(): AudioContext {
  if (!_audioContext) {
    _audioContext = new AudioContext()
  }
  return _audioContext
}

/** Call from a user-gesture handler to unlock audio for the session. */
function unlockAudio(): void {
  const ctx = _getOrCreateContext()
  if (ctx.state === 'suspended') {
    ctx.resume().catch((e) => logger.warn('AudioContext resume failed:', e))
  }
}

function _stopCurrentAudio(): void {
  if (_currentSource) {
    try { _currentSource.stop() } catch { /* already stopped */ }
    _currentSource = null
  }
  _chunkQueue = []
  _isPlayingChunks = false
  isSpeaking.value = false
}

async function _playAudioBuffer(arrayBuffer: ArrayBuffer): Promise<void> {
  const ctx = _getOrCreateContext()
  if (ctx.state === 'suspended') await ctx.resume()
  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
  const source = ctx.createBufferSource()
  source.buffer = audioBuffer
  source.connect(ctx.destination)
  _currentSource = source
  isSpeaking.value = true

  return new Promise<void>((resolve) => {
    source.onended = () => {
      if (_currentSource === source) {
        _currentSource = null
      }
      resolve()
    }
    source.start(0)
  })
}

async function _drainChunkQueue(): Promise<void> {
  if (_isPlayingChunks) return
  _isPlayingChunks = true

  while (_chunkQueue.length > 0) {
    const chunk = _chunkQueue.shift()!
    try {
      await _playAudioBuffer(chunk)
    } catch (e) {
      logger.error('Chunk playback error:', e)
    }
  }

  _isPlayingChunks = false
  isSpeaking.value = false
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

  async function speak(text: string, force?: boolean): Promise<void> {
    if ((!force && !voiceOutputEnabled.value) || !text.trim()) return
    if (isSpeaking.value) _stopCurrentAudio()

    try {
      const { effectiveVoiceId } = useVoiceProfiles()
      const formData = new FormData()
      formData.append('text', text)
      if (effectiveVoiceId.value) {
        formData.append('voice_id', effectiveVoiceId.value)
      }
      const response = await fetchWithAuth('/api/voice/synthesize', {
        method: 'POST',
        body: formData,
      })
      if (!response.ok) {
        logger.warn('TTS synthesize failed:', response.status)
        return
      }
      const blob = await response.blob()
      const arrayBuffer = await blob.arrayBuffer()
      await _playAudioBuffer(arrayBuffer)
    } catch (e) {
      logger.error('speak() error:', e)
      isSpeaking.value = false
    }
  }

  /** Queue a base64-encoded WAV chunk for sequential playback (#1031). */
  function playAudioChunk(base64Data: string): void {
    try {
      const binary = atob(base64Data)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i)
      }
      _chunkQueue.push(bytes.buffer)
      isSpeaking.value = true
      _drainChunkQueue()
    } catch (e) {
      logger.error('playAudioChunk error:', e)
    }
  }

  /** Stop any current or queued audio immediately (#1031). */
  function stopSpeaking(): void {
    _stopCurrentAudio()
  }

  return {
    voiceOutputEnabled,
    isSpeaking,
    toggleVoiceOutput,
    speak,
    unlockAudio,
    playAudioChunk,
    stopSpeaking,
  }
}
