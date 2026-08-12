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
import i18n from '@/i18n'

const logger = createLogger('useVoiceOutput')

const STORAGE_KEY = 'autobot-voice-output-enabled'

// #13215: chunked TTS wire format. The backend answers /voice/synthesize with
// `[4-byte big-endian length][WAV]` frames when `stream=true` is sent, marked
// by this header, so the first ~250ms can play while the rest is still being
// synthesized. Must stay in step with api/voice.py's AUDIO_STREAM_FRAMING*.
const FRAMING_HEADER = 'X-Audio-Framing'
const FRAMING_VALUE = 'length-prefixed-wav'
const FRAME_HEADER_BYTES = 4

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

// ── #12460: adaptive pre-roll so a below-real-time worker still plays smoothly ──
//
// Gapless scheduling only holds while the worker produces audio at least as fast
// as it is consumed. On a loaded host it does not: 19 of 19 measured syntheses
// ran at 0.09x-0.83x real time. Each chunk is then already late when it arrives,
// _scheduleGaplessChunk re-anchors it to ctx.currentTime, and the listener hears
// ~250ms of speech per gap — the reported stutter.
//
// Fix: hold decoded chunks until enough audio is buffered for the REST of the
// utterance to play out continuously. For an utterance of D audio-seconds
// produced at r audio-seconds per wall-second, playback that starts with B
// seconds buffered stays gapless iff B >= (1 - r) * D — consumed time t must
// never exceed produced audio B + r*t, and the binding case is t = D.
//
// D is estimated from the utterance text; r is measured from chunk arrivals and
// carried ACROSS utterances, because it is a property of the worker and its host,
// not of the sentence. With no measurement yet (first utterance of a session) or
// a worker at/above real time, nothing is held back and the #13215 first-audio
// latency is untouched.
//
// Audio still scheduled ahead of the playhead is lead-in too, but it is NOT
// worth its own duration: while A seconds of an earlier sentence play out, the
// worker adds only r*A. Extending the derivation over A + D of playout gives
// B >= (1 - r) * D - r * A, so scheduled-ahead audio is credited at r*A.
const _RTF_TARGET = 1.0
// Upper bound on the lead-in in AUDIO-seconds.
const _PREROLL_MAX_SEC = 8
// ...and the bound that actually caps latency. Buffering B audio-seconds at rate
// r costs B/r of WALL time, so an audio-seconds cap alone is not a wait bound: at
// the 0.09x measured in #12460 an 8s target is ~90s of silence before speech.
// Affordable buffer within this wait is MAX_WAIT*r, so the slowest workers buy
// less lead-in rather than an unbounded delay — they stutter, and the
// below-real-time alert is what surfaces the real problem.
const _PREROLL_MAX_WAIT_SEC = 8
// Stall watchdog, NOT a cap on filling the lead-in: filling T audio-seconds at
// rate r legitimately takes T/r wall-seconds, so a total-duration timer would
// force-release exactly the slow workers this exists for. Re-armed on every held
// chunk, it only fires when the worker has genuinely stopped producing.
const _PREROLL_STALL_MS = 10_000
// Audio-seconds per character, used to size D before any audio exists. Measured
// on the deploy in #12460: 49 chars -> ~3.3s, 209 chars -> ~11.4s of audio.
const _SEC_PER_CHAR = 0.06
// Weight of the newest per-utterance sample in the carried real-time factor.
const _RTF_SMOOTHING = 0.3
// Shortest window a production rate may be derived from. Two chunks that
// arrive coalesced a few ms apart otherwise compute as ~100x, drive the
// target to zero and release the pre-roll for good — the mirror image of the
// transient gap already handled below.
const _RTF_MIN_WINDOW_SEC = 0.5

// Carried production rate in audio-seconds per wall-second; null until measured.
let _measuredRtf: number | null = null
// Decoded chunks held back during the current utterance's lead-in.
let _pendingBuffers: AudioBuffer[] = []
let _pendingSec = 0
let _utteranceHolding = false
let _utterancePrerollSec = 0
let _utteranceEstimateSec = 0
// Rate this utterance is being sized against — the carried rate, lowered if the
// utterance turns out to be producing even more slowly than that.
let _utteranceRtf = 0
// Bumped per utterance so a chunk that finishes decoding after its own
// utterance ended is not folded into the next one's buffer or rate.
let _utteranceSeq = 0
// Bumped by every explicit stop, so a chunk decoded after a barge-in is
// dropped rather than spoken as a fragment of the superseded reply.
let _stopSeq = 0
let _prerollTimer: ReturnType<typeof setTimeout> | null = null
// Arrival wall-clock of this utterance's FIRST chunk. Time-to-first-chunk is
// model warm-up, not production rate, so the rate is measured from chunk 2 on.
let _rtfFirstChunkAt = 0
let _rtfProducedSec = 0
// Arrival of the LAST observed chunk. The carried rate is measured to here, not
// to tts_end: the final chunk is often still decoding when the utterance ends,
// so measuring to "now" left its arrival interval in the window with its audio
// missing and biased the worker slow.
let _rtfLastChunkAt = 0

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

// #11802: shared in-flight voice-list fetch. useApiResource aborts the prior
// request on every new load(), so concurrent voice checks must await ONE
// fetch instead of racing and cancelling each other.
let _voicesFetchInFlight: Promise<void> | null = null

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type VoiceMessage = Record<string, any>
type VoiceMessageHandler = (msg: VoiceMessage) => void
const _voiceSubscribers = new Set<VoiceMessageHandler>()
const wsConnected = ref<boolean>(false)

// AbortController for the current in-flight speak() HTTP request.
// Module-level so a new speak() call can abort the previous one.
let _speakController: AbortController | null = null

// #12502: sequential fallback queue. When the TTS WebSocket is unavailable,
// speakStreaming() falls back to per-sentence HTTP synthesis. Routing each
// sentence through speak() aborted the in-flight utterance, so only the LAST
// sentence of a reply was heard. Instead, enqueue sentences and drain them
// sequentially (await each before starting the next) so the full reply is
// spoken. An intentional stop / new reply clears _speakQueue and aborts
// _speakController via _stopCurrentAudio(), which breaks the drain loop.
const _speakQueue: string[] = []
let _speakDraining = false

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
 *
 * #11802: concurrent callers share ONE in-flight fetch. Per-sentence
 * streaming calls speak() several times at once; each check used to call
 * fetchVoices() independently, and useApiResource's `abortPrior` default
 * cancels the previous in-flight request — so the checks aborted each other
 * (nginx 499), left `voices` empty, and fired the "no voices" message on a
 * deployment whose voices were fine.
 */
async function _hasVoicesAvailable(): Promise<boolean> {
  const { voices, fetchVoices } = useVoiceProfiles()
  if (voices.value.length === 0) {
    if (_voicesFetchInFlight === null) {
      _voicesFetchInFlight = fetchVoices().finally(() => {
        _voicesFetchInFlight = null
      })
    }
    try {
      await _voicesFetchInFlight
    } catch (e) {
      // An aborted/failed fetch is NOT evidence of a zero-voice deployment,
      // so stay quiet and let the next call re-check (#11802).
      logger.warn('fetchVoices failed during TTS voice check:', e)
      return voices.value.length > 0
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

// #12503: browser autoplay policy only unlocks a suspended AudioContext from
// inside a real user gesture. The WS streaming path plays from an onmessage
// handler (not a gesture), so a resume() there leaves the context suspended and
// every scheduled buffer is silent. When we detect that at playback time, arm a
// one-time global gesture listener that resumes the context so the NEXT reply
// plays, and surface a "tap to enable audio" hint instead of a silent, stuck
// "speaking" indicator.
const _GESTURE_UNLOCK_EVENTS = ['pointerdown', 'keydown', 'touchstart'] as const
let _gestureUnlockHandler: (() => void) | null = null

function _disarmGestureUnlock(): void {
  if (!_gestureUnlockHandler) return
  for (const evt of _GESTURE_UNLOCK_EVENTS) {
    window.removeEventListener(evt, _gestureUnlockHandler)
  }
  _gestureUnlockHandler = null
}

function _armGestureUnlock(): void {
  if (_gestureUnlockHandler) return
  const handler = (): void => {
    _disarmGestureUnlock()
    const ctx = _audioContext
    if (ctx && ctx.state === 'suspended') {
      ctx.resume().catch((e) => logger.warn('AudioContext resume failed:', e))
    }
  }
  _gestureUnlockHandler = handler
  for (const evt of _GESTURE_UNLOCK_EVENTS) {
    window.addEventListener(evt, handler, { passive: true })
  }
}

// #12503: suppress repeat "tap to enable audio" hints within a short window so
// a burst of tts_audio chunks against a suspended context surfaces it once.
let _tapHintNotifiedAt = 0
function _notifyTapToEnableAudio(): void {
  const now = Date.now()
  if (now - _tapHintNotifiedAt < _NO_VOICES_NOTIFY_COOLDOWN) return
  _tapHintNotifiedAt = now
  logger.warn('AudioContext suspended at playback — awaiting user gesture to unlock')
  useToast().showToast(i18n.global.t('voice.tapToEnableAudio'), 'info')
}

/** Call from a user-gesture handler to unlock audio for the session. */
function unlockAudio(): void {
  const ctx = _getOrCreateContext()
  if (ctx.state === 'suspended') {
    ctx.resume().catch((e) => logger.warn('AudioContext resume failed:', e))
  }
  // A fresh gesture just unlocked (or is unlocking) the context — no need to
  // keep a pending one-time listener armed.
  _disarmGestureUnlock()
}

function _stopCurrentAudio(): void {
  // #12502: an intentional stop / new reply must cancel ALL pending audio —
  // drop any queued fallback sentences and abort the in-flight synthesis so the
  // drain loop stops instead of continuing to speak a superseded reply.
  _speakQueue.length = 0
  _speakController?.abort()
  // #12460: audio still inside the pre-roll buffer belongs to the superseded
  // reply — dropping it here is what makes barge-in immediate. Bumping the stop
  // sequence also discards chunks still being decoded, which no flag could
  // otherwise reach.
  _stopSeq++
  _resetPreroll()
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
  if (ctx.state === 'suspended') {
    await ctx.resume().catch((e) => logger.warn('AudioContext resume failed:', e))
  }
  if (ctx.state === 'suspended') {
    // #12503: still suspended outside a user gesture — playback would be silent
    // and onended would never fire, hanging this promise and sticking the
    // indicator. Re-arm a gesture listener, hint the user, and return quietly.
    _armGestureUnlock()
    _notifyTapToEnableAudio()
    isSpeaking.value = false
    return
  }
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

/** Discard the pre-roll buffer and its timer without playing anything (#12460). */
function _resetPreroll(): void {
  if (_prerollTimer) {
    clearTimeout(_prerollTimer)
    _prerollTimer = null
  }
  _pendingBuffers = []
  _pendingSec = 0
  _utteranceHolding = false
  _utterancePrerollSec = 0
  _utteranceEstimateSec = 0
  _utteranceRtf = 0
  _rtfFirstChunkAt = 0
  _rtfProducedSec = 0
  _rtfLastChunkAt = 0
}

/**
 * Lead-in credited to this utterance (#12460): what is held in the pre-roll
 * buffer, plus what the worker will produce while audio already scheduled ahead
 * plays out — r*A, not A. Crediting scheduled-ahead audio at full value would
 * release a follow-on sentence far too early, since a sentence queued behind
 * 5 seconds of playout still only gains 5*r seconds of production from it.
 */
function _leadSec(rtf: number): number {
  const ahead = _audioContext ? Math.max(0, _nextStartTime - _audioContext.currentTime) : 0
  return _pendingSec + rtf * ahead
}

/** Place one decoded buffer on the gapless timeline (#1527). */
function _scheduleBuffer(ctx: AudioContext, audioBuffer: AudioBuffer): void {
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
      // Not idle if the NEXT sentence is already buffering: clearing here fires
      // watch(isSpeaking) in useVoiceConversation, which reopens the mic in the
      // gap between sentences (#12460).
      if (!_utteranceHolding) isSpeaking.value = false
    }
  }

  source.start(startTime)
  // #12503: flag "speaking" only once a buffer is actually scheduled on a
  // RUNNING context — never before decode/resume — so the indicator reflects
  // real audio and a suspended/failed chunk cannot leave it stuck on.
  isSpeaking.value = true
}

/** Hand every held chunk to the timeline and stop holding back (#12460). */
function _releasePending(): void {
  if (_prerollTimer) {
    clearTimeout(_prerollTimer)
    _prerollTimer = null
  }
  _utteranceHolding = false
  if (_pendingBuffers.length === 0) {
    _pendingSec = 0
    return
  }
  const ctx = _getOrCreateContext()
  const buffers = _pendingBuffers
  _pendingBuffers = []
  _pendingSec = 0
  if (ctx.state === 'suspended') {
    // The context was running when these chunks were held but the tab has been
    // backgrounded since. Starting sources on a frozen timeline never fires
    // onended, which is exactly how the indicator used to stick (#12503).
    // Put them back rather than discarding them: this can be up to the whole
    // lead-in, i.e. the opening of the reply. The next chunk, the end of the
    // utterance, or an explicit stop retries or clears them — no timer is
    // re-armed here, so a still-suspended context cannot spin.
    _pendingBuffers = buffers
    _pendingSec = buffers.reduce((total, buffer) => total + buffer.duration, 0)
    _utteranceHolding = true
    _armGestureUnlock()
    _notifyTapToEnableAudio()
    if (_activeChunkCount <= 0) isSpeaking.value = false
    return
  }
  for (const buffer of buffers) _scheduleBuffer(ctx, buffer)
}

/** (Re)arm the stall watchdog for the current hold (#12460). */
function _armStallTimer(): void {
  if (_prerollTimer) clearTimeout(_prerollTimer)
  _prerollTimer = setTimeout(() => {
    _prerollTimer = null
    logger.warn('TTS pre-roll stalled; playing what is buffered')
    _releasePending()
  }, _PREROLL_STALL_MS)
}

/**
 * Fold one chunk into the production-rate measurement and return the live rate
 * for this utterance, or null while it is not yet measurable (#12460).
 */
function _observeChunkRate(durationSec: number): number | null {
  const now = Date.now()
  _rtfLastChunkAt = now
  if (_rtfFirstChunkAt === 0) {
    _rtfFirstChunkAt = now
    return null
  }
  _rtfProducedSec += durationSec
  const elapsedSec = (now - _rtfFirstChunkAt) / 1000
  if (elapsedSec < _RTF_MIN_WINDOW_SEC) return null
  return _rtfProducedSec / elapsedSec
}

/** Blend an utterance's measured production rate into the carried one (#12460). */
function _recordRtfSample(sample: number): void {
  _measuredRtf =
    _measuredRtf === null ? sample : _measuredRtf + _RTF_SMOOTHING * (sample - _measuredRtf)
}

/** Lead-in needed for `estimateSec` of audio produced at `rtf` (#12460). */
function _prerollTargetSec(rtf: number, estimateSec: number): number {
  if (rtf >= _RTF_TARGET || rtf <= 0) return 0
  const derived = (1 - rtf) * estimateSec
  // Bounded by audio-seconds AND by what fits in the wall-clock wait budget.
  return Math.max(0, Math.min(derived, _PREROLL_MAX_SEC, _PREROLL_MAX_WAIT_SEC * rtf))
}

/**
 * Open an utterance: decide from the carried real-time factor whether its audio
 * must be pre-rolled before playback starts (#12460).
 */
function _beginUtterance(text: string): void {
  // A previous utterance's held audio is never dropped on a boundary — only an
  // explicit stop discards it.
  _releasePending()
  _resetPreroll()
  _utteranceSeq++
  const rtf = _measuredRtf
  if (rtf === null) return
  _utteranceRtf = rtf
  _utteranceEstimateSec = text.trim().length * _SEC_PER_CHAR
  _utterancePrerollSec = _prerollTargetSec(rtf, _utteranceEstimateSec)
  if (_utterancePrerollSec <= 0) return
  _utteranceHolding = true
  // The watchdog is armed by the first held chunk, NOT here: a slow first chunk
  // would otherwise fire it against an empty buffer, and that release clears
  // _utteranceHolding — silently disabling pre-roll for the whole utterance.
}

/**
 * Close an utterance: flush whatever is still held — a short utterance may never
 * reach its lead-in target, and its tail must still be spoken (#12460) — then
 * carry the measured production rate to the next utterance.
 */
function _endUtterance(): void {
  _releasePending()
  const elapsedSec =
    _rtfFirstChunkAt > 0 && _rtfLastChunkAt > _rtfFirstChunkAt
      ? (_rtfLastChunkAt - _rtfFirstChunkAt) / 1000
      : 0
  if (elapsedSec > 0 && _rtfProducedSec > 0) {
    _recordRtfSample(_rtfProducedSec / elapsedSec)
  }
  _rtfFirstChunkAt = 0
  _rtfProducedSec = 0
  _rtfLastChunkAt = 0
  _utterancePrerollSec = 0
  _utteranceEstimateSec = 0
  _utteranceRtf = 0
}

/**
 * Schedule an audio chunk for gapless playback on the AudioContext timeline (#1527).
 * Instead of awaiting each chunk sequentially (which causes gaps during decode),
 * we decode immediately and schedule at the next available time slot.
 *
 * #12460: while the utterance is pre-rolling, the decoded chunk is held instead,
 * and everything held is released the moment the lead-in covers the rest of the
 * utterance at the observed production rate.
 */
async function _scheduleGaplessChunk(arrayBuffer: ArrayBuffer): Promise<void> {
  const seq = _utteranceSeq
  const stopSeq = _stopSeq
  const ctx = _getOrCreateContext()
  if (ctx.state === 'suspended') {
    // A resume() from the WS onmessage handler is not a user gesture; try once,
    // then bail if the context stays suspended (#12503).
    await ctx.resume().catch((e) => logger.warn('AudioContext resume failed:', e))
  }
  if (ctx.state === 'suspended') {
    // Autoplay policy still blocks playback — no audio will be heard. Re-arm a
    // one-time gesture listener + surface a hint, and DON'T set isSpeaking so the
    // indicator can't stick with no sound (#12503).
    _armGestureUnlock()
    _notifyTapToEnableAudio()
    return
  }

  const audioBuffer = await ctx.decodeAudioData(arrayBuffer.slice(0))

  if (stopSeq !== _stopSeq) {
    // A stop / barge-in landed while this chunk was decoding. It belongs to a
    // reply the user has already dismissed, so it is dropped outright — playing
    // it would speak a fragment and flip isSpeaking back on after stopSpeaking().
    return
  }

  if (seq !== _utteranceSeq) {
    // Decoding is genuinely async, so the previous utterance's last chunk often
    // resolves after the next tts_start. It belongs to the reply already being
    // played — schedule it straight through rather than holding it with, and
    // skewing the rate of, an utterance it is not part of.
    _scheduleBuffer(ctx, audioBuffer)
    return
  }

  const liveRtf = _observeChunkRate(audioBuffer.duration)

  if (!_utteranceHolding) {
    _scheduleBuffer(ctx, audioBuffer)
    return
  }

  _pendingBuffers.push(audioBuffer)
  _pendingSec += audioBuffer.duration
  // #12460: the reply IS being spoken — it is buffering, not finished. Leaving
  // isSpeaking false here would fire watch(isSpeaking) in useVoiceConversation,
  // expiring the TTS echo cooldown and reopening the mic mid-reply.
  isSpeaking.value = true
  _armStallTimer()
  if (liveRtf !== null) {
    // Track the live rate in both directions. _observeChunkRate is cumulative
    // over the utterance, so it is already smooth; ratcheting it downward instead
    // let one transient arrival gap pin the target at the cap for the rest of
    // the utterance with no way to recover.
    _utteranceRtf = liveRtf
    _utterancePrerollSec = _prerollTargetSec(liveRtf, _utteranceEstimateSec)
  }
  if (_leadSec(_utteranceRtf) >= _utterancePrerollSec) _releasePending()
}

/** Decode base64 audio and schedule for gapless playback (#1527). */
async function _playAudioChunkFromBase64(base64Data: string): Promise<void> {
  let bytes: Uint8Array<ArrayBuffer>
  try {
    const binary = atob(base64Data)
    bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
  } catch (e) {
    logger.error('playAudioChunk decode error:', e)
    return
  }
  try {
    // #12503: await + catch so a decode/scheduling rejection is handled, not
    // swallowed, and never leaves the "speaking" indicator stuck.
    await _scheduleGaplessChunk(bytes.buffer)
  } catch (e) {
    logger.error('playAudioChunk playback error:', e)
    if (_activeChunkCount <= 0) isSpeaking.value = false
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
      if (msg.type === 'tts_start') {
        // #12460: the utterance's text sizes its pre-roll before any audio exists.
        _beginUtterance(typeof msg.text === 'string' ? msg.text : '')
      } else if (msg.type === 'tts_audio' && msg.data) {
        void _playAudioChunkFromBase64(msg.data)
      } else if (msg.type === 'tts_end') {
        // #12460: the backend sends tts_end even on a mid-stream failure, so this
        // is also what guarantees held audio is never stranded.
        _endUtterance()
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

/**
 * Read the backend's `[4-byte big-endian length][WAV]` framing, scheduling each
 * mini-WAV the instant it arrives (#13215).
 *
 * The chunks are separate, independently-decodable WAV files — concatenating
 * them and handing the result to decodeAudioData would only ever decode the
 * first one, so they must be split here and scheduled individually on the same
 * gapless timeline the WebSocket path uses.
 */
async function _playFramedAudioStream(body: ReadableStream<Uint8Array>): Promise<void> {
  const reader = body.getReader()
  let buffer = new Uint8Array(0)
  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (value?.length) {
        const merged = new Uint8Array(buffer.length + value.length)
        merged.set(buffer)
        merged.set(value, buffer.length)
        buffer = merged
      }
      // Drain every complete frame currently buffered before reading again.
      for (;;) {
        if (buffer.length < FRAME_HEADER_BYTES) break
        const view = new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength)
        const size = view.getUint32(0, false)
        if (buffer.length < FRAME_HEADER_BYTES + size) break
        // A zero-length frame is reachable: readexactly(0) returns b'' without
        // raising, so a 0 header from the worker propagates an empty chunk.
        // decodeAudioData rejects on it, which would abandon every remaining
        // frame of the utterance — skip it instead.
        if (size === 0) {
          buffer = buffer.slice(FRAME_HEADER_BYTES)
          continue
        }
        const wav = buffer.slice(FRAME_HEADER_BYTES, FRAME_HEADER_BYTES + size)
        buffer = buffer.slice(FRAME_HEADER_BYTES + size)
        // One undecodable frame must not silence the rest of the reply — the
        // WebSocket path already guards per-chunk this way.
        try {
          await _scheduleGaplessChunk(wav.buffer as ArrayBuffer)
        } catch (error) {
          logger.warn('TTS frame decode failed; skipping frame', error)
        }
      }
      if (done) break
    }
  } finally {
    // Releases the response body on an abort or a throw; without this the
    // stream stays locked and the connection is never cancelled.
    reader.cancel().catch(() => {})
  }
  if (buffer.length > 0) {
    logger.warn('TTS stream ended mid-frame; dropped', buffer.length, 'trailing bytes')
  }
}

/**
 * Synthesize `text` via the HTTP TTS endpoint and play it to completion.
 * Shared by the one-shot speak() and the sequential fallback drainer (#12502).
 * The caller owns the AbortController so it can cancel this request.
 *
 * Requests the chunked variant (#13215): the backend then emits each ~250ms
 * mini-WAV as the worker produces it instead of buffering the whole utterance,
 * which is what made every spoken reply start after 4.7–10.1s of silence. A
 * runtime without ReadableStream support still gets the whole-blob response.
 */
async function _synthesizeAndPlay(text: string, signal: AbortSignal): Promise<void> {
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
  formData.append('stream', 'true')
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
  if (response.headers.get(FRAMING_HEADER) === FRAMING_VALUE && response.body) {
    // Chunks are scheduled on the shared gapless timeline and are still
    // sounding when this resolves, so isSpeaking is left to the per-source
    // onended handler — clearing it here would drop the indicator (and fire
    // watch(isSpeaking)) while audio is mid-utterance.
    // #12460: the end of the framed body IS the end of the utterance, so the
    // pre-roll is closed in `finally` — an abort or a truncated stream must
    // still flush whatever was held rather than swallow it.
    _beginUtterance(text)
    try {
      await _playFramedAudioStream(response.body)
    } finally {
      _endUtterance()
    }
    return
  }
  const blob = await response.blob()
  const arrayBuffer = await blob.arrayBuffer()
  await _playAudioBuffer(arrayBuffer)
  // Issue #1146: clear isSpeaking so watch(isSpeaking) in useVoiceConversation fires
  isSpeaking.value = false
}

/**
 * Drain the fallback queue, playing one sentence at a time to completion (#12502).
 * Never aborts the in-flight utterance itself, so a burst of enqueued sentences
 * plays end-to-end. Only an external stop (which clears the queue + aborts the
 * controller) ends the loop early.
 */
async function _drainSpeakQueue(): Promise<void> {
  _speakDraining = true
  try {
    while (_speakQueue.length > 0) {
      const next = _speakQueue.shift() as string
      _speakController = new AbortController()
      try {
        await _synthesizeAndPlay(next, _speakController.signal)
      } catch (e) {
        if (e instanceof DOMException && (e as DOMException).name === 'AbortError') {
          // Intentional stop / new reply cleared the queue — stop draining.
          break
        }
        logger.error('queued speak() error:', e)
        isSpeaking.value = false
      }
    }
  } finally {
    _speakDraining = false
  }
}

/**
 * Enqueue a sentence for sequential HTTP playback (#12502). Used by the
 * speakStreaming() fallback so per-sentence calls never abort each other.
 */
function _enqueueFallbackSpeak(text: string): void {
  if (!text.trim()) return
  _speakQueue.push(text)
  if (_speakDraining) return
  void _drainSpeakQueue()
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

  // One-shot speak: aborts any in-flight/queued audio first (intentional-abort
  // semantics for a new one-shot utterance / manual replacement). Per-sentence
  // streaming does NOT go through here — it uses speakStreaming() + the
  // sequential fallback queue so sentences never abort each other (#12502).
  async function speak(text: string, force?: boolean): Promise<void> {
    if ((!force && !voiceOutputEnabled.value) || !text.trim()) return
    // #12460: a superseded reply may be mid-pre-roll rather than mid-playback.
    // Without the holding check the stop is skipped, and _beginUtterance's
    // release then speaks the superseded audio first — the #12502 failure.
    if (isSpeaking.value || _utteranceHolding) _stopCurrentAudio()

    // #9999: surface a clear message instead of failing silently when the
    // deployment has no TTS voices installed.
    if (!(await _hasVoicesAvailable())) return

    _speakController?.abort()
    _speakController = new AbortController()

    try {
      await _synthesizeAndPlay(text, _speakController.signal)
    } catch (e) {
      if (e instanceof DOMException && (e as DOMException).name === 'AbortError') return
      logger.error('speak() error:', e)
      isSpeaking.value = false
    }
  }

  /** Queue a base64-encoded WAV chunk for sequential playback (#1031). */
  function playAudioChunk(base64Data: string): void {
    void _playAudioChunkFromBase64(base64Data)
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
      // #12502: enqueue for sequential playback — calling speak() per sentence
      // aborted the in-flight utterance, so only the last sentence was heard.
      logger.warn('TTS WS unavailable, falling back to queued HTTP synthesis')
      _enqueueFallbackSpeak(text.trim())
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
