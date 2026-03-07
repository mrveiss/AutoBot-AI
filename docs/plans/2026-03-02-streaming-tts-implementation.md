# Streaming Sentence-Level TTS Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify all voice modes through WebSocket streaming with sentence-level TTS — first audio plays within ~1.5-3s instead of waiting 5-15s for the full LLM response.

**Architecture:** Frontend sentence accumulator detects complete sentences during LLM SSE streaming, sends each via WS `speak_sentence` to a backend queue worker that synthesizes and streams audio chunks back. Existing `playAudioChunk()` queue handles sequential playback.

**Tech Stack:** FastAPI WebSocket (backend), Vue 3 + TypeScript composable (frontend), asyncio queue (sentence worker), existing Pocket TTS client

**Design Doc:** `docs/plans/2026-03-02-streaming-tts-design.md`
**Issue:** #1319

---

## Task 1: Backend — `_tts_queue_worker` coroutine

**Files:**
- Modify: `autobot-backend/api/voice_stream.py:26-36` (imports + module vars)
- Modify: `autobot-backend/api/voice_stream.py:82-132` (after `_synthesize_and_stream`)
- Test: manual WebSocket test with `websocat` or Python script

**Step 1: Add the `_tts_queue_worker` coroutine after `_synthesize_and_stream`**

After line 132 (end of `_synthesize_and_stream`), add the queue worker:

```python
async def _tts_queue_worker(
    ws: WebSocket,
    queue: asyncio.Queue,
    cancel_event: asyncio.Event,
) -> None:
    """Drain the sentence queue, synthesizing and streaming each sequentially.

    Runs as a background task per WS connection. Receives (text, voice_id)
    tuples; None is the flush sentinel that triggers tts_end.
    """
    while True:
        item = await queue.get()
        if item is None:
            # flush sentinel — no more sentences coming
            await _send_json(ws, {"type": "tts_end"})
            continue
        text, voice_id = item
        if cancel_event.is_set():
            continue  # skip queued sentences on barge-in
        try:
            tts = get_tts_client()
            wav_bytes = await tts.synthesize(text, voice_id=voice_id)
            if cancel_event.is_set():
                continue
            audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
            await _send_json(ws, {
                "type": "tts_audio",
                "data": audio_b64,
            })
        except Exception as e:
            logger.error("Sentence TTS error: %s", e)
            await _send_json(ws, {
                "type": "error",
                "message": f"Sentence TTS failed: {e}",
            })
```

**Step 2: Verify the file still parses**

Run: `cd /home/kali/Desktop/AutoBot && python3 -c "import ast; ast.parse(open('autobot-backend/api/voice_stream.py').read()); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add autobot-backend/api/voice_stream.py
git commit -m "feat(voice): add _tts_queue_worker for sentence-level streaming (#1319)"
```

---

## Task 2: Backend — `speak_sentence` + `flush` message handlers + queue wiring

**Files:**
- Modify: `autobot-backend/api/voice_stream.py:179-241` (the `voice_stream_ws` function)

**Step 1: Add sentence queue + worker task to the WS handler**

In `voice_stream_ws()`, after `tts_task: Optional[asyncio.Task] = None` (line 186), add:

```python
    sentence_queue: asyncio.Queue = asyncio.Queue()
    queue_worker_task: Optional[asyncio.Task] = None
```

After `await _set_state("idle")` (line 195), start the worker:

```python
        queue_worker_task = asyncio.create_task(
            _tts_queue_worker(websocket, sentence_queue, cancel_tts)
        )
```

**Step 2: Add `speak_sentence` and `flush` message handlers**

After the `speak` handler block (line 226), add:

```python
            elif msg_type == "speak_sentence":
                text = msg.get("text", "").strip()
                voice_id = msg.get("voice_id", "")
                if text:
                    await sentence_queue.put((text, voice_id))

            elif msg_type == "flush":
                await sentence_queue.put(None)  # sentinel
```

**Step 3: Update barge-in to clear the sentence queue**

In the `barge_in` handler (around line 200-203), after `await _cancel_active_tts(cancel_tts, tts_task)`, add queue drain:

```python
                # Clear pending sentences on barge-in
                while not sentence_queue.empty():
                    try:
                        sentence_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
```

**Step 4: Clean up queue worker in finally block**

In the `finally` block (line 236-240), add before the existing cleanup:

```python
        if queue_worker_task and not queue_worker_task.done():
            queue_worker_task.cancel()
            try:
                await queue_worker_task
            except asyncio.CancelledError:
                pass
```

**Step 5: Verify syntax**

Run: `cd /home/kali/Desktop/AutoBot && python3 -c "import ast; ast.parse(open('autobot-backend/api/voice_stream.py').read()); print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add autobot-backend/api/voice_stream.py
git commit -m "feat(voice): add speak_sentence/flush WS handlers with queue wiring (#1319)"
```

---

## Task 3: Frontend — Lazy WS connection + `speakStreaming()` + `flushStreaming()` in useVoiceOutput.ts

**Files:**
- Modify: `autobot-frontend/src/composables/useVoiceOutput.ts:1-177` (full file)

**Step 1: Add WS imports and module-level state**

After the existing module-level variables (after line 33, the `_isPlayingChunks` declaration), add:

```typescript
// Streaming TTS WebSocket connection (#1319)
let _ttsWs: WebSocket | null = null
let _ttsWsIdleTimer: ReturnType<typeof setTimeout> | null = null
const _TTS_WS_IDLE_TIMEOUT = 30_000 // close WS after 30s idle
```

**Step 2: Add `_connectTtsWs()` private function**

After `_getOrCreateContext()` (line 40), add:

```typescript
function _connectTtsWs(): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    if (_ttsWs && _ttsWs.readyState === WebSocket.OPEN) {
      _resetTtsWsIdleTimer()
      resolve(_ttsWs)
      return
    }
    // Close stale connection if exists
    if (_ttsWs) {
      try { _ttsWs.close() } catch { /* ignore */ }
      _ttsWs = null
    }

    const { getBackendWsUrl } = await_import_ssot()
    const url = getBackendWsUrl('/api/voice/stream')
    const ws = new WebSocket(url)

    ws.onopen = () => {
      _ttsWs = ws
      _resetTtsWsIdleTimer()
      logger.debug('TTS WS connected')
      resolve(ws)
    }
    ws.onerror = (e) => {
      logger.warn('TTS WS error:', e)
      _ttsWs = null
      reject(e)
    }
    ws.onclose = () => {
      logger.debug('TTS WS closed')
      _ttsWs = null
    }
    ws.onmessage = (event) => {
      _resetTtsWsIdleTimer()
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'tts_audio' && msg.data) {
          playAudioChunkInternal(msg.data)
        } else if (msg.type === 'tts_end') {
          // Sentence stream complete — isSpeaking cleared by chunk drain
        } else if (msg.type === 'error') {
          logger.warn('TTS WS server error:', msg.message)
        }
      } catch (e) {
        logger.warn('TTS WS message parse error:', e)
      }
    }
  })
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
```

**Important:** The `_connectTtsWs` function uses a Promise pattern because WS connection is async. We need to handle the import of `getBackendWsUrl` — it's already imported in useVoiceConversation.ts, but we need to add it to useVoiceOutput.ts.

Add to the imports at the top (after line 13):

```typescript
import { getBackendWsUrl } from '@/config/ssot-config'
```

And simplify the WS URL construction (no `await_import_ssot()`, just use the import directly):

```typescript
const url = getBackendWsUrl('/api/voice/stream')
```

**Step 3: Add `playAudioChunkInternal()` — extract from existing `playAudioChunk()`**

The existing `playAudioChunk()` (line 148) decodes base64 and queues. Extract the core logic so the WS `onmessage` handler can call it without re-exporting:

Rename the inner logic — actually, since `playAudioChunk` is already defined inside `useVoiceOutput()`, and the WS handler is at module level, we need a module-level version. The simplest approach: move the base64→ArrayBuffer decode + queue push + drain trigger to module level.

Replace existing `playAudioChunk` (lines 148-161) with a module-level `_playAudioChunkFromBase64`:

```typescript
function _playAudioChunkFromBase64(base64Data: string): void {
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
```

Then inside `useVoiceOutput()`, define `playAudioChunk` as a thin wrapper:

```typescript
function playAudioChunk(base64Data: string): void {
  _playAudioChunkFromBase64(base64Data)
}
```

And update the WS `onmessage` to call `_playAudioChunkFromBase64(msg.data)`.

**Step 4: Add `speakStreaming()` and `flushStreaming()` inside `useVoiceOutput()`**

After the `stopSpeaking()` function (line 166), add:

```typescript
  /** Send a single sentence for streaming TTS via WebSocket (#1319).
   *  Falls back to HTTP speak() if WS is unavailable. */
  async function speakStreaming(text: string): Promise<void> {
    if (!text.trim()) return
    try {
      const ws = await _connectTtsWs()
      const { effectiveVoiceId } = useVoiceProfiles()
      ws.send(JSON.stringify({
        type: 'speak_sentence',
        text: text.trim(),
        voice_id: effectiveVoiceId.value || '',
      }))
    } catch {
      // WS unavailable — fall back to HTTP speak
      logger.warn('TTS WS unavailable, falling back to HTTP speak()')
      await speak(text, true)
    }
  }

  /** Signal end of sentence stream — backend sends tts_end after queue drains (#1319). */
  async function flushStreaming(): Promise<void> {
    try {
      const ws = await _connectTtsWs()
      ws.send(JSON.stringify({ type: 'flush' }))
    } catch {
      // WS unavailable — nothing to flush
    }
  }
```

**Step 5: Update the return object**

Add `speakStreaming`, `flushStreaming`, and `_disconnectTtsWs` (for cleanup) to the return:

```typescript
  return {
    voiceOutputEnabled,
    isSpeaking,
    toggleVoiceOutput,
    speak,
    speakStreaming,
    flushStreaming,
    unlockAudio,
    playAudioChunk,
    stopSpeaking,
  }
```

**Step 6: Verify no TypeScript errors**

Run: `cd /home/kali/Desktop/AutoBot/autobot-frontend && npx vue-tsc --noEmit --pretty 2>&1 | head -20`
(May take a while; if no TS errors in the file, proceed)

**Step 7: Commit**

```bash
git add autobot-frontend/src/composables/useVoiceOutput.ts
git commit -m "feat(voice): add WS connection + speakStreaming/flushStreaming (#1319)"
```

---

## Task 4: Frontend — Sentence accumulator watcher in ChatInterface.vue

**Files:**
- Modify: `autobot-frontend/src/components/chat/ChatInterface.vue:861-884` (auto-speak watcher)

**Step 1: Update imports**

In the `<script setup>` section, find the existing `useVoiceOutput()` destructure. Add `speakStreaming` and `flushStreaming`:

Change:
```typescript
const { voiceOutputEnabled, speak, ... } = useVoiceOutput()
```
To include:
```typescript
const { voiceOutputEnabled, speak, speakStreaming, flushStreaming, ... } = useVoiceOutput()
```

**Step 2: Replace the auto-speak watcher**

Replace lines 861-884 (the current auto-speak watcher) with the sentence accumulator:

```typescript
// Streaming sentence-level TTS (#1319)
// During LLM streaming: extract completed sentences and send each to TTS immediately.
// After streaming: flush remainder. Falls back to HTTP speak() if WS unavailable.
const _SPEAKABLE_TYPES = new Set(['response', 'message'])
let _lastSpokenIdx = 0
let _lastStreamingMsgId: string | null = null

watch(
  () => {
    // Find the last speakable assistant message
    const session = store.sessions.find(s => s.id === store.currentSessionId)
    const msgs = session?.messages ?? []
    for (let i = msgs.length - 1; i >= 0; i--) {
      const m = msgs[i]
      if (m.sender !== 'assistant' || !m.content) continue
      if (m.type && !_SPEAKABLE_TYPES.has(m.type)) continue
      return { id: m.id, content: m.content }
    }
    return null
  },
  (current, previous) => {
    if (!voiceOutputEnabled.value || voiceConversation.isActive.value) return
    if (!current) return

    // Reset index when message changes
    if (current.id !== _lastStreamingMsgId) {
      _lastSpokenIdx = 0
      _lastStreamingMsgId = current.id
    }

    if (store.isTyping && current.content) {
      // During streaming: extract and speak completed sentences
      const newText = current.content.slice(_lastSpokenIdx)
      const sentences = _extractCompleteSentences(newText)
      for (const s of sentences) {
        speakStreaming(s)
        _lastSpokenIdx += s.length
      }
    } else if (!store.isTyping && current.content) {
      // Stream ended: flush any remaining text
      const remainder = current.content.slice(_lastSpokenIdx).trim()
      if (remainder) speakStreaming(remainder)
      flushStreaming()
      _lastSpokenIdx = 0
      _lastStreamingMsgId = null
    }
  }
)

/** Extract sentences terminated by ". ", "! ", or "? " — remainder stays buffered. */
function _extractCompleteSentences(text: string): string[] {
  const sentences: string[] = []
  const terminators = /(?<=[.!?])\s+/g
  let lastEnd = 0
  let match
  while ((match = terminators.exec(text)) !== null) {
    sentences.push(text.slice(lastEnd, match.index + 1))
    lastEnd = match.index + match[0].length
  }
  return sentences
}
```

**Step 3: Commit**

```bash
git add autobot-frontend/src/components/chat/ChatInterface.vue
git commit -m "feat(voice): replace auto-speak watcher with sentence accumulator (#1319)"
```

---

## Task 5: Frontend — Update `_dispatchTranscript()` in useVoiceConversation.ts

**Files:**
- Modify: `autobot-frontend/src/composables/useVoiceConversation.ts:381-438` (`_dispatchTranscript`)

**Step 1: Import `speakStreaming` and `flushStreaming`**

In the `_dispatchTranscript()` function (line 384), update the destructure:

Change:
```typescript
  const { speak, isSpeaking } = useVoiceOutput()
```
To:
```typescript
  const { speak, speakStreaming, flushStreaming, isSpeaking } = useVoiceOutput()
```

**Step 2: Replace the non-duplex speak path**

The current code (lines 428-437) for walkie-talkie/hands-free:

```typescript
    if (mode.value === 'full-duplex' && wsConnected.value) {
      const { effectiveVoiceId } = useVoiceProfiles()
      _sendWs({ type: 'speak', text: speechText, voice_id: effectiveVoiceId.value })
    } else {
      state.value = 'speaking'
      speak(speechText, true).then(() => {
        if (!isSpeaking.value && state.value === 'speaking') {
          state.value = 'idle'
        }
      })
    }
```

Replace the `else` branch with streaming TTS:

```typescript
    if (mode.value === 'full-duplex' && wsConnected.value) {
      const { effectiveVoiceId } = useVoiceProfiles()
      _sendWs({ type: 'speak', text: speechText, voice_id: effectiveVoiceId.value })
    } else {
      // Use streaming TTS for walkie-talkie and hands-free (#1319)
      state.value = 'speaking'
      speakStreaming(speechText)
      flushStreaming()
      // Resume listening when audio finishes
      const unwatch = watch(isSpeaking, (speaking) => {
        if (!speaking && state.value === 'speaking') {
          unwatch()
          _resumeAutoListening()
        }
      })
    }
```

Note: `_resumeAutoListening()` (line 370) is the correct function to call — it handles mode-specific resume logic (full-duplex restarts listening, hands-free re-enables VAD).

**Step 3: Commit**

```bash
git add autobot-frontend/src/composables/useVoiceConversation.ts
git commit -m "feat(voice): use streaming TTS in _dispatchTranscript (#1319)"
```

---

## Task 6: Update WS protocol documentation in voice_stream.py header

**Files:**
- Modify: `autobot-backend/api/voice_stream.py:1-24` (docstring)

**Step 1: Add new message types to the protocol doc**

Update the docstring to include the new message types:

```python
"""
Voice Stream WebSocket Endpoint (#1031, #1319)

Provides a bidirectional WebSocket for voice conversations.
Supports full-duplex mode AND sentence-level streaming TTS for all modes.

Protocol (JSON messages):
  Client -> Server:
    {"type": "barge_in"}              - User interrupted TTS playback
    {"type": "transcript", "text": "...", "final": true/false}
    {"type": "start_listening"}       - Client started STT capture
    {"type": "stop_listening"}        - Client stopped STT capture
    {"type": "speak", "text": "..."}  - Full-text TTS (cancels active, for duplex)
    {"type": "speak_sentence", "text": "...", "voice_id": "..."}  - Queue sentence (#1319)
    {"type": "flush"}                 - Signal end of sentence stream (#1319)
    {"type": "ping"}

  Server -> Client:
    {"type": "state", "state": "idle|listening|processing|speaking"}
    {"type": "tts_start", "text": "..."}   - TTS synthesis beginning
    {"type": "tts_audio", "data": "<base64>", "chunk": N, "total": N}
    {"type": "tts_end"}                     - TTS playback complete
    {"type": "error", "message": "..."}
    {"type": "pong"}
"""
```

**Step 2: Commit**

```bash
git add autobot-backend/api/voice_stream.py
git commit -m "docs(voice): update WS protocol doc for speak_sentence/flush (#1319)"
```

---

## Task 7: Manual Integration Test

**Step 1: Verify backend starts without import errors**

Run: `cd /home/kali/Desktop/AutoBot && python3 -c "from api.voice_stream import router; print('Router OK:', router.routes)"`
Expected: No import errors

**Step 2: Test WS protocol manually**

Use a Python script to test the new message types:

```python
import asyncio
import json
import websockets

async def test():
    async with websockets.connect("wss://172.16.168.20:8443/api/voice/stream", ssl=...) as ws:
        # Should receive initial state
        msg = await ws.recv()
        print("State:", msg)

        # Send a sentence
        await ws.send(json.dumps({
            "type": "speak_sentence",
            "text": "Hello, this is a test.",
            "voice_id": ""
        }))

        # Flush
        await ws.send(json.dumps({"type": "flush"}))

        # Should receive tts_audio + tts_end
        while True:
            msg = json.loads(await ws.recv())
            print("Got:", msg["type"])
            if msg["type"] == "tts_end":
                break

asyncio.run(test())
```

**Step 3: Test in browser**

1. Open AutoBot frontend
2. Enable voice output toggle
3. Send a message to the LLM
4. Verify: first audio plays while response is still streaming
5. Verify: all sentences play sequentially
6. Verify: barge-in (sending new message) cancels queued audio

**Step 4: Close issue**

```bash
gh issue close 1319 --comment "Implemented streaming sentence-level TTS. All voice modes now use WS streaming with sentence accumulator. Time-to-first-audio reduced from ~5-15s to ~1.5-3s."
```

---

## Summary of Changes

| File | Lines Changed | What |
|---|---|---|
| `autobot-backend/api/voice_stream.py` | +50 | `_tts_queue_worker`, `speak_sentence`/`flush` handlers, barge-in queue drain |
| `autobot-frontend/src/composables/useVoiceOutput.ts` | +80 | WS connection mgmt, `speakStreaming()`, `flushStreaming()`, module-level chunk helper |
| `autobot-frontend/src/components/chat/ChatInterface.vue` | +40/-20 | Sentence accumulator replaces wait-for-complete watcher |
| `autobot-frontend/src/composables/useVoiceConversation.ts` | +10/-5 | `_dispatchTranscript()` uses streaming TTS |
