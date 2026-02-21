/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useVoiceConversation.ts - Voice conversation state machine (#1029, #1030, #1031)
 * Manages walkie-talkie, hands-free, and full-duplex voice conversation modes.
 * Hands-free uses Silero VAD + server-side Whisper transcription (#1030).
 * Full-duplex uses WebSocket signaling + AudioWorklet VAD for barge-in (#1031).
 */

import { ref, computed, watch } from 'vue'
import type { ChatMessage } from '@/stores/useChatStore'
import { useVoiceOutput } from '@/composables/useVoiceOutput'
import { useChatController } from '@/models/controllers'
import { useChatStore } from '@/stores/useChatStore'
import { getBackendWsUrl } from '@/config/ssot-config'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
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
const wsConnected = ref(false)

// Hands-free mode state (#1030)
const silenceThreshold = ref(1500)
const audioLevel = ref(0)

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _recognition: any = null
let _ws: WebSocket | null = null
let _vadAudioCtx: AudioContext | null = null
let _vadNode: AudioWorkletNode | null = null
let _micStream: MediaStream | null = null
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _sileroVad: any = null

// Response message types that should be spoken (skip thoughts/planning/debug)
const _SPEAKABLE_TYPES = new Set(['response', 'message'])

// Max chars to send to TTS — Kani-TTS-2 on CPU takes ~10s per sentence
const _MAX_SPEECH_CHARS = 200

function _generateId(): string {
  return `vb_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

/** Strip tool-call markup and truncate to a TTS-safe length. */
function _sanitizeForSpeech(text: string): string {
  const clean = text
    .replace(/<TOOL_CALL[^>]*>|<\/TOOL_CALL>/gi, '')
    .replace(/<[^>]+>/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (clean.length <= _MAX_SPEECH_CHARS) return clean
  const truncated = clean.slice(0, _MAX_SPEECH_CHARS)
  const lastBreak = Math.max(
    truncated.lastIndexOf('. '),
    truncated.lastIndexOf('! '),
    truncated.lastIndexOf('? '),
  )
  return lastBreak > 50 ? truncated.slice(0, lastBreak + 1) : truncated
}

// ─── WebSocket helpers ───────────────────────────────────

function _connectWs(): void {
  if (_ws && _ws.readyState <= WebSocket.OPEN) return

  const base = getBackendWsUrl()
  const url = `${base}/api/voice/stream`
  logger.debug('Connecting voice WS:', url)

  _ws = new WebSocket(url)

  _ws.onopen = () => {
    wsConnected.value = true
    logger.debug('Voice WS connected')
  }

  _ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data)
      _handleWsMessage(msg)
    } catch (e) {
      logger.error('Voice WS parse error:', e)
    }
  }

  _ws.onclose = () => {
    wsConnected.value = false
    logger.debug('Voice WS disconnected')
    if (mode.value === 'full-duplex' && isActive.value) {
      logger.warn('WS dropped — falling back to walkie-talkie')
      mode.value = 'walkie-talkie'
      errorMessage.value = 'Connection lost. Switched to walkie-talkie.'
    }
  }

  _ws.onerror = (e) => {
    logger.error('Voice WS error:', e)
  }
}

function _disconnectWs(): void {
  if (_ws) {
    try { _ws.close() } catch { /* ignore */ }
    _ws = null
  }
  wsConnected.value = false
}

function _sendWs(data: Record<string, unknown>): void {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(data))
  }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function _handleWsMessage(msg: any): void {
  const { playAudioChunk } = useVoiceOutput()

  switch (msg.type) {
    case 'state':
      logger.debug('Server state:', msg.state)
      break
    case 'tts_start':
      state.value = 'speaking'
      break
    case 'tts_audio':
      playAudioChunk(msg.data)
      break
    case 'tts_end':
      // Handled by isSpeaking watcher when audio queue drains
      break
    case 'error':
      logger.error('Server voice error:', msg.message)
      errorMessage.value = msg.message
      break
    case 'pong':
      break
  }
}

function _onSpeakingDone(): void {
  state.value = 'idle'
  if (!isActive.value) return
  if (mode.value === 'full-duplex') {
    _startListeningInternal()
  } else if (mode.value === 'hands-free' && _sileroVad) {
    // Hands-free auto-resumes via Silero VAD (already running)
    state.value = 'listening'
  }
}

// ─── AudioWorklet VAD helpers ────────────────────────────

async function _initVad(): Promise<void> {
  if (_vadAudioCtx) return

  try {
    _micStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    _vadAudioCtx = new AudioContext()
    await _vadAudioCtx.audioWorklet.addModule('/audio-vad-processor.js')

    const source = _vadAudioCtx.createMediaStreamSource(_micStream)
    _vadNode = new AudioWorkletNode(_vadAudioCtx, 'vad-processor')

    _vadNode.port.onmessage = (event) => {
      const { speaking } = event.data
      if (speaking && state.value === 'speaking') {
        _handleBargeIn()
      }
    }

    source.connect(_vadNode)
    logger.debug('VAD AudioWorklet initialized')
  } catch (e) {
    logger.error('VAD init failed:', e)
    errorMessage.value = 'Mic access required for full-duplex mode.'
  }
}

function _teardownVad(): void {
  if (_vadNode) {
    _vadNode.disconnect()
    _vadNode = null
  }
  if (_vadAudioCtx) {
    _vadAudioCtx.close().catch(() => {})
    _vadAudioCtx = null
  }
  if (_micStream) {
    _micStream.getTracks().forEach((t) => t.stop())
    _micStream = null
  }
}

function _handleBargeIn(): void {
  logger.debug('Barge-in detected')
  const { stopSpeaking } = useVoiceOutput()
  stopSpeaking()
  _sendWs({ type: 'barge_in' })
  state.value = 'idle'
  _startListeningInternal()
}

// ─── STT helper (shared across modes) ───────────────────

function _startListeningInternal(): void {
  if (state.value === 'listening') return
  if (!isActive.value) return

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const w = window as any
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition
  if (!Ctor) {
    errorMessage.value = 'Voice input requires Chrome, Edge, or Safari 15+.'
    return
  }

  _recognition = new Ctor()
  _recognition.continuous = mode.value === 'full-duplex'
  _recognition.interimResults = true
  _recognition.lang = 'en-US'

  _recognition.onstart = () => {
    state.value = 'listening'
    currentTranscript.value = ''
    _sendWs({ type: 'start_listening' })
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  _recognition.onresult = (event: any) => {
    let interim = ''
    let finalText = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const r = event.results[i]
      if (r.isFinal) {
        finalText += r[0].transcript
      } else {
        interim += r[0].transcript
      }
    }

    if (finalText && mode.value === 'full-duplex') {
      currentTranscript.value = ''
      const text = finalText.trim()
      if (text) {
        try { _recognition?.abort() } catch { /* ok */ }
        _recognition = null
        _dispatchTranscript(text)
      }
    } else if (finalText) {
      // Walkie-talkie: accumulate (onend sends)
      currentTranscript.value = finalText
    } else {
      currentTranscript.value = interim
    }
  }

  _recognition.onend = () => {
    _sendWs({ type: 'stop_listening' })

    if (mode.value !== 'full-duplex') {
      const text = currentTranscript.value.trim()
      if (text) {
        _dispatchTranscript(text)
      } else {
        state.value = 'idle'
      }
    } else if (isActive.value && state.value === 'listening') {
      setTimeout(() => {
        if (isActive.value && state.value === 'idle') {
          _startListeningInternal()
        }
      }, 100)
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
    } else if (event.error === 'no-speech') {
      if (mode.value === 'full-duplex' && isActive.value) {
        state.value = 'idle'
        setTimeout(() => _startListeningInternal(), 200)
        return
      }
    } else if (event.error !== 'aborted') {
      errorMessage.value = `Speech error: ${event.error}`
    }
    state.value = 'idle'
  }

  _recognition.start()
}

function _stopRecognition(): void {
  if (_recognition) {
    try { _recognition.abort() } catch { /* ignore */ }
    _recognition = null
  }
  currentTranscript.value = ''
}

/** Process a finalized transcript: add bubble, send to LLM, speak response. */
function _dispatchTranscript(text: string): void {
  const store = useChatStore()
  const controller = useChatController()
  const { speak, isSpeaking } = useVoiceOutput()

  state.value = 'processing'
  _sendWs({ type: 'transcript', text, final: true })

  bubbles.value.push({
    id: _generateId(),
    sender: 'user',
    content: text,
    timestamp: Date.now(),
  })

  controller.sendMessage(text, { use_knowledge: false }).then(() => {
    const session = store.sessions.find(
      (s) => s.id === store.currentSessionId,
    )
    const msgs: ChatMessage[] = session?.messages ?? []
    let response: string | null = null
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i]
      if (m.sender !== 'assistant' || !m.content) continue
      if (m.type && !_SPEAKABLE_TYPES.has(m.type)) continue
      response = m.content
      break
    }

    if (!response || !isActive.value) {
      state.value = 'idle'
      if (mode.value === 'full-duplex') _startListeningInternal()
      return
    }

    bubbles.value.push({
      id: _generateId(),
      sender: 'assistant',
      content: response,
      timestamp: Date.now(),
    })

    const speechText = _sanitizeForSpeech(response)
    if (!speechText) {
      state.value = 'idle'
      if (mode.value === 'full-duplex') _startListeningInternal()
      return
    }

    if (mode.value === 'full-duplex' && wsConnected.value) {
      _sendWs({ type: 'speak', text: speechText })
    } else {
      state.value = 'speaking'
      speak(speechText, true).then(() => {
        if (!isSpeaking.value && state.value === 'speaking') {
          state.value = 'idle'
        }
      })
    }
  }).catch((err) => {
    logger.error('Failed to send voice transcript:', err)
    errorMessage.value = 'Failed to send message. Try again.'
    state.value = 'idle'
    if (mode.value === 'full-duplex') _startListeningInternal()
  })
}

// ─── Hands-free VAD helpers (#1030) ─────────────────────

function _writeWavStr(view: DataView, off: number, s: string): void {
  for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i))
}

/** Convert Float32Array PCM samples to a WAV Blob (16-bit, mono). */
function _float32ToWav(samples: Float32Array, sr: number): Blob {
  const len = samples.length
  const buf = new ArrayBuffer(44 + len * 2)
  const v = new DataView(buf)
  _writeWavStr(v, 0, 'RIFF')
  v.setUint32(4, 36 + len * 2, true)
  _writeWavStr(v, 8, 'WAVE')
  _writeWavStr(v, 12, 'fmt ')
  v.setUint32(16, 16, true)
  v.setUint16(20, 1, true)
  v.setUint16(22, 1, true)
  v.setUint32(24, sr, true)
  v.setUint32(28, sr * 2, true)
  v.setUint16(32, 2, true)
  v.setUint16(34, 16, true)
  _writeWavStr(v, 36, 'data')
  v.setUint32(40, len * 2, true)
  for (let i = 0; i < len; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([buf], { type: 'audio/wav' })
}

/** POST audio blob to /api/voice/transcribe → { text, confidence }. */
async function _transcribeAudio(blob: Blob): Promise<string> {
  const form = new FormData()
  form.append('audio', blob, 'speech.wav')
  const res = await fetchWithAuth('/api/voice/transcribe', {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    logger.warn('Transcribe failed:', res.status)
    return ''
  }
  const data = await res.json()
  return (data.text ?? '').trim()
}

/** Start Silero VAD for hands-free speech detection (#1030). */
async function _startHandsFree(): Promise<void> {
  if (_sileroVad) return
  state.value = 'listening'
  try {
    const { MicVAD } = await import('@ricky0123/vad-web')
    _sileroVad = await MicVAD.new({
      positiveSpeechThreshold: 0.8,
      minSpeechMs: 150,
      redemptionMs: 250,
      onSpeechEnd: (audio: Float32Array) => {
        _handleVadSpeechEnd(audio)
      },
      onFrameProcessed: (probs) => {
        audioLevel.value = probs.isSpeech
      },
    })
    _sileroVad.start()
    logger.debug('Silero VAD started (hands-free)')
  } catch (e) {
    logger.error('Silero VAD init failed:', e)
    errorMessage.value = 'Mic access required for hands-free mode.'
    state.value = 'idle'
  }
}

function _stopHandsFree(): void {
  if (_sileroVad) {
    try { _sileroVad.destroy() } catch { /* ignore */ }
    _sileroVad = null
  }
  audioLevel.value = 0
}

/** Called by Silero VAD when speech ends: encode, transcribe, dispatch. */
function _handleVadSpeechEnd(audio: Float32Array): void {
  if (!isActive.value || state.value !== 'listening') return
  state.value = 'processing'
  const wavBlob = _float32ToWav(audio, 16000)
  _transcribeAudio(wavBlob)
    .then((text) => {
      if (!text || !isActive.value) {
        state.value = 'idle'
        return
      }
      _dispatchTranscript(text)
    })
    .catch((err) => {
      logger.error('Hands-free transcription error:', err)
      errorMessage.value = 'Transcription failed. Try again.'
      state.value = 'idle'
    })
}

// ─── Main composable ────────────────────────────────────

export function useVoiceConversation() {
  const { isSpeaking, unlockAudio, stopSpeaking } = useVoiceOutput()

  const isListening = computed(() => state.value === 'listening')
  const isProcessing = computed(() => state.value === 'processing')

  const stateLabel = computed(() => {
    const duplex = mode.value === 'full-duplex'
    switch (state.value) {
      case 'idle':
        return duplex ? 'Ready — speak anytime' : 'Tap to speak'
      case 'listening': return 'Listening...'
      case 'processing': return 'Processing...'
      case 'speaking':
        return duplex
          ? 'Speaking — interrupt anytime'
          : 'AutoBot is speaking...'
      default: return ''
    }
  })

  async function activate(): Promise<void> {
    isActive.value = true
    state.value = 'idle'
    bubbles.value = []
    errorMessage.value = ''
    unlockAudio()

    if (mode.value === 'full-duplex') {
      _connectWs()
      await _initVad()
      _startListeningInternal()
    } else if (mode.value === 'hands-free') {
      await _startHandsFree()
    }
    logger.debug('Voice conversation activated, mode:', mode.value)
  }

  function deactivate(): void {
    _stopRecognition()
    _stopHandsFree()
    _disconnectWs()
    _teardownVad()
    stopSpeaking()
    isActive.value = false
    state.value = 'idle'
    currentTranscript.value = ''
    logger.debug('Voice conversation deactivated')
  }

  function startListening(): void {
    if (state.value === 'speaking' && mode.value === 'full-duplex') {
      _handleBargeIn()
      return
    }
    if (state.value !== 'idle') return
    unlockAudio()
    _startListeningInternal()
  }

  function stopListening(): void {
    if (_recognition) _recognition.stop()
  }

  function toggleListening(): void {
    if (state.value === 'listening') {
      stopListening()
    } else if (state.value === 'idle') {
      startListening()
    } else if (
      state.value === 'speaking' && mode.value === 'full-duplex'
    ) {
      _handleBargeIn()
    }
  }

  function setMode(newMode: ConversationMode): void {
    if (mode.value === newMode) return
    const wasActive = isActive.value

    if (wasActive) {
      _stopRecognition()
      _stopHandsFree()
      _disconnectWs()
      _teardownVad()
      stopSpeaking()
      state.value = 'idle'
      currentTranscript.value = ''
    }

    mode.value = newMode

    if (wasActive && newMode === 'full-duplex') {
      _connectWs()
      _initVad().then(() => _startListeningInternal())
    } else if (wasActive && newMode === 'hands-free') {
      _startHandsFree()
    }
    logger.debug('Mode switched to:', newMode)
  }

  // Watch isSpeaking to handle TTS completion
  watch(isSpeaking, (speaking) => {
    if (!speaking && state.value === 'speaking') {
      _onSpeakingDone()
    }
  })

  function cleanup(): void {
    deactivate()
  }

  return {
    state,
    mode,
    currentTranscript,
    bubbles,
    isActive,
    errorMessage,
    wsConnected,
    audioLevel,
    isListening,
    isProcessing,
    stateLabel,
    activate,
    deactivate,
    startListening,
    stopListening,
    toggleListening,
    setMode,
    cleanup,
  }
}
