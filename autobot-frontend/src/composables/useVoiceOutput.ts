// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
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
import { usePreferences } from '@/composables/usePreferences'
import { useToast } from '@/composables/useToast'
import { getBackendWsUrl, getApiBase } from '@/config/ssot-config'

const logger = createLogger('useVoiceOutput')

const STORAGE_KEY = 'autobot-voice-output-enabled'

// #9999: user-visible message when a deployment has no TTS voices installed
// (e.g. no tts-worker provisioned in small topologies). Without this, TTS
// no-ops silently and the operator gets no feedback.
const NO_VOICES_MESSAGE =
  'Text-to-speech is not available on this deployment — no speech voices are installed.'

// Module-level singletons so state is shared across component instances
const voiceOutputEnabled = ref<boolean>(
  localStorage.getItem(STORAGE_KEY) === 'true'
)
const isSpeaking = ref<boolean>(false)

// AudioContext survives expired user gestures — once resumed, it stays unlocked.
// new Audio().play() requires a fresh gesture each time and fails after delay.
let _audioContext: AudioContext | null = null
let _currentSource: AudioBufferSourceNode | null = null

// Gapless audio scheduling (#1527) — schedule chunks on AudioContext timeline
// instead of sequential play-await-decode-play which causes audible gaps.
let _scheduledSources: AudioBufferSourceNode[] = []
let _nextStartTime = 0
let _activeChunkCount = 0

// Single shared WebSocket to /api/voice/stream (#6788).
// Was: useVoiceOutput + useVoiceConversation each opened their own socket to the
// same endpoint, causing diverging backend state machines and dropped TTS on the
// second turn. This composable is now the sole owner; consumers subscribe via
// subscribeVoiceMessages() and send via sendVoiceFrame().
let _ttsWs: WebSocket | null = null
let _ttsWsConnecting: Promise<WebSocket> | null = null
let _ttsWsIdleTimer: ReturnType<typeof setTimeout> | null = null
const _TTS_WS_IDLE_TIMEOUT = 30_000

// #9999: suppress repeat "no voices" toasts within a short window so a burst of
// speak() calls (e.g. per-sentence streaming) surfaces the message only once.
let _noVoicesNotifiedAt = 0
const _NO_VOICES_NOTIFY_COOLDOWN = 30_000

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type VoiceMessage = Record<string, any>
type VoiceMessageHandler = (msg: VoiceMessage) => void
const _voiceSubscribers = new Set<VoiceMessageHandler>()
const wsConnected = ref<boolean>(false)

// AbortController for the current in-flight speak() HTTP request.
// Module-level so a new speak() call can abort the previous one.
let _speakController: AbortController | null = null

/**
 * #9999: Surface the "no voices available" message once per cooldown window.
 * Uses the app's standard toast mechanism so the operator gets feedback
 * instead of TTS silently no-op'ing.
 */
function _notifyNoVoices(): void {
  const now = Date.now()
  if (now - _noVoicesNotifiedAt < _NO_VOICES_NOTIFY_COOLDOWN) return
  _noVoicesNotifiedAt = now
  logger.warn('TTS attempted with zero available voices')
  useToast().showToast(NO_VOICES_MESSAGE, 'warning')
}

/**
 * #9999: Return true when at least one TTS voice is available, otherwise
 * surface a user-visible message and return false. Lazily fetches the voice
 * list once if it has not been loaded yet (it is normally only populated by
 * the settings panel), so an empty list reflects a genuine zero-voices
 * deployment rather than an unfetched cache.
 */
async function _hasVoicesAvailable(): Promise<boolean> {
  const { voices, fetchVoices } = useVoiceProfiles()
  if (voices.value.length === 0) {
    try {
      await fetchVoices()
    } catch (e) {
      logger.warn('fetchVoices failed during TTS voice check:', e)
    }
  }
  if (voices.value.length === 0) {
    _notifyNoVoices()
    return false
  }
  return true
}

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
  // Stop all scheduled gapless sources (#1527)
  for (const src of _scheduledSources) {
    try { src.stop() } catch { /* already stopped */ }
  }
  _scheduledSources = []
  _nextStartTime = 0
  _activeChunkCount = 0
  isSpeaking.value = false
}

async function _playAudioBuffer(arrayBuffer: ArrayBuffer): Promise<void> {
  const ctx = _getOrCreateContext()
  if (ctx.state === 'suspended') await ctx.resume()
  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
  const source = ctx.createBufferSource()
  source.buffer = audioBuffer
  // Issue #1146: Amplify TTS output — Pocket TTS generates lower-amplitude audio
  const gainNode = ctx.createGain()
  gainNode.gain.value = 3.5
  source.connect(gainNode)
  gainNode.connect(ctx.destination)
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

/**
 * Schedule an audio chunk for gapless playback on the AudioContext timeline (#1527).
 * Instead of awaiting each chunk sequentially (which causes gaps during decode),
 * we decode immediately and schedule at the next available time slot.
 */
async function _scheduleGaplessChunk(arrayBuffer: ArrayBuffer): Promise<void> {
  const ctx = _getOrCreateContext()
  if (ctx.state === 'suspended') await ctx.resume()

  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))
  const source = ctx.createBufferSource()
  source.buffer = audioBuffer

  const gainNode = ctx.createGain()
  gainNode.gain.value = 3.5
  source.connect(gainNode)
  gainNode.connect(ctx.destination)

  // Schedule gaplessly: start where the last chunk ends, or now if behind
  const now = ctx.currentTime
  const startTime = _nextStartTime > now ? _nextStartTime : now
  _nextStartTime = startTime + audioBuffer.duration

  _scheduledSources.push(source)
  _activeChunkCount++

  source.onended = () => {
    const idx = _scheduledSources.indexOf(source)
    if (idx >= 0) _scheduledSources.splice(idx, 1)
    _activeChunkCount--
    if (_activeChunkCount <= 0) {
      _activeChunkCount = 0
      isSpeaking.value = false
    }
  }

  source.start(startTime)
}

/** Decode base64 audio and schedule for gapless playback (#1527). */
function _playAudioChunkFromBase64(base64Data: string): void {
  try {
    const binary = atob(base64Data)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
    isSpeaking.value = true
    _scheduleGaplessChunk(bytes.buffer)
  } catch (e) {
    logger.error('playAudioChunk error:', e)
  }
}

function _resetTtsWsIdleTimer(): void {
  if (_ttsWsIdleTimer) clearTimeout(_ttsWsIdleTimer)
  _ttsWsIdleTimer = setTimeout(() => {
    if (_ttsWs) {
      _ttsWs.close()
      _ttsWs = null
    }
  }, _TTS_WS_IDLE_TIMEOUT)
}

function _disconnectTtsWs(): void {
  if (_ttsWsIdleTimer) {
    clearTimeout(_ttsWsIdleTimer)
    _ttsWsIdleTimer = null
  }
  if (_ttsWs) {
    try { _ttsWs.close() } catch { /* ignore */ }
    _ttsWs = null
  }
}

function _connectTtsWs(): Promise<WebSocket> {
  if (_ttsWs && _ttsWs.readyState === WebSocket.OPEN) {
    _resetTtsWsIdleTimer()
    return Promise.resolve(_ttsWs)
  }
  // Guard against concurrent connection attempts (#1420) — return the
  // in-flight promise so only ONE WebSocket is created at a time.
  if (_ttsWsConnecting) {
    return _ttsWsConnecting
  }
  if (_ttsWs) {
    try { _ttsWs.close() } catch { /* ignore */ }
    _ttsWs = null
  }

  _ttsWsConnecting = new Promise<WebSocket>((resolve, reject) => {
    const url = `${getBackendWsUrl()}/api/voice/stream`
    const ws = new WebSocket(url)

    ws.onopen = () => {
      _ttsWs = ws
      _ttsWsConnecting = null
      wsConnected.value = true
      _resetTtsWsIdleTimer()
      logger.debug('Voice WS connected')
      resolve(ws)
    }
    ws.onerror = (e) => {
      logger.warn('Voice WS error:', e)
      _ttsWs = null
      _ttsWsConnecting = null
      wsConnected.value = false
      reject(e)
    }
    ws.onclose = () => {
      logger.debug('Voice WS closed')
      _ttsWs = null
      _ttsWsConnecting = null
      wsConnected.value = false
    }
    ws.onmessage = (event) => {
      _resetTtsWsIdleTimer()
      let msg: VoiceMessage
      try {
        msg = JSON.parse(event.data)
      } catch (e) {
        logger.warn('Voice WS message parse error:', e)
        return
      }
      // Internal: audio playback owned here.
      if (msg.type === 'tts_audio' && msg.data) {
        _playAudioChunkFromBase64(msg.data)
      } else if (msg.type === 'error') {
        logger.warn('Voice WS server error:', msg.message)
      }
      // Fan-out to external subscribers (state machine, transcripts, etc.)
      for (const handler of _voiceSubscribers) {
        try { handler(msg) } catch (e) { logger.warn('voice subscriber error:', e) }
      }
    }
  })
  return _ttsWsConnecting
}

export function useVoiceOutput() {
  function toggleVoiceOutput(): void {
    voiceOutputEnabled.value = !voiceOutputEnabled.value
    localStorage.setItem(STORAGE_KEY, String(voiceOutputEnabled.value))
    logger.debug('Voice output toggled:', voiceOutputEnabled.value)
    if (voiceOutputEnabled.value) {
      // Issue #1146: unlock AudioContext from the user-gesture click event so
      // future speak() calls (triggered by reactive watchers, not gestures) can
      // play audio without hitting the browser autoplay policy.
      unlockAudio()
    } else {
      _stopCurrentAudio()
    }
  }

  async function speak(text: string, force?: boolean): Promise<void> {
    if ((!force && !voiceOutputEnabled.value) || !text.trim()) return
    if (isSpeaking.value) _stopCurrentAudio()

    // #9999: surface a clear message instead of failing silently when the
    // deployment has no TTS voices installed.
    if (!(await _hasVoicesAvailable())) return

    _speakController?.abort()
    _speakController = new AbortController()
    const signal = _speakController.signal

    try {
      const { effectiveVoiceId } = useVoiceProfiles()
      const { language: prefLang } = usePreferences()
      const language = prefLang.value || ''
      const formData = new FormData()
      formData.append('text', text)
      if (effectiveVoiceId.value) {
        formData.append('voice_id', effectiveVoiceId.value)
      }
      if (language) {
        formData.append('language', language)
      }
      const response = await fetchWithAuth(`${getApiBase()}/voice/synthesize`, { // fetchWithAuth retained: binary audio blob + FormData body — exempt (#6256)
        method: 'POST',
        body: formData,
        signal,
      })
      if (!response.ok) {
        logger.warn('TTS synthesize failed:', response.status)
        // #9999: 404/503 here means no TTS service/voices on this deployment.
        if (response.status === 404 || response.status === 503) {
          _notifyNoVoices()
        }
        return
      }
      const blob = await response.blob()
      const arrayBuffer = await blob.arrayBuffer()
      await _playAudioBuffer(arrayBuffer)
      // Issue #1146: clear isSpeaking so watch(isSpeaking) in useVoiceConversation fires
      isSpeaking.value = false
    } catch (e) {
      if (e instanceof DOMException && (e as DOMException).name === 'AbortError') return
      logger.error('speak() error:', e)
      isSpeaking.value = false
    }
  }

  /** Queue a base64-encoded WAV chunk for sequential playback (#1031). */
  function playAudioChunk(base64Data: string): void {
    _playAudioChunkFromBase64(base64Data)
  }

  /** Stop any current or queued audio immediately (#1031). */
  function stopSpeaking(): void {
    _stopCurrentAudio()
  }

  async function speakStreaming(text: string): Promise<void> {
    if (!text.trim()) return
    // #9999: surface a clear message instead of failing silently when the
    // deployment has no TTS voices installed.
    if (!(await _hasVoicesAvailable())) return
    try {
      const ws = await _connectTtsWs()
      const { effectiveVoiceId } = useVoiceProfiles()
      const { language: prefLang } = usePreferences()
      const language = prefLang.value || ''
      ws.send(JSON.stringify({
        type: 'speak_sentence',
        text: text.trim(),
        voice_id: effectiveVoiceId.value || '',
        language,
      }))
    } catch {
      logger.warn('TTS WS unavailable, falling back to HTTP speak()')
      await speak(text, true)
    }
  }

  async function flushStreaming(): Promise<void> {
    try {
      const ws = await _connectTtsWs()
      ws.send(JSON.stringify({ type: 'flush' }))
    } catch {
      // WS unavailable — nothing to flush
    }
  }

  /**
   * Subscribe to inbound voice WS messages (#6788). Returns an unsubscribe fn.
   * The subscription drives lazy connection: first subscribe opens the socket;
   * audio playback (`tts_audio`) is still handled internally by this composable.
   */
  function subscribeVoiceMessages(handler: VoiceMessageHandler): () => void {
    _voiceSubscribers.add(handler)
    _connectTtsWs().catch(() => { /* logged inside */ })
    return () => { _voiceSubscribers.delete(handler) }
  }

  /** Send a frame on the shared voice WS, lazy-connecting if needed (#6788). */
  async function sendVoiceFrame(payload: VoiceMessage): Promise<void> {
    try {
      const ws = await _connectTtsWs()
      ws.send(JSON.stringify(payload))
    } catch {
      logger.warn('sendVoiceFrame: WS unavailable')
    }
  }

  return {
    voiceOutputEnabled,
    isSpeaking,
    wsConnected,
    toggleVoiceOutput,
    speak,
    speakStreaming,
    flushStreaming,
    unlockAudio,
    playAudioChunk,
    stopSpeaking,
    subscribeVoiceMessages,
    sendVoiceFrame,
  }
}
