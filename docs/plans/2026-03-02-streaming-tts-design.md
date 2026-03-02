# Streaming Sentence-Level TTS Design

**Issue:** #1319
**Date:** 2026-03-02
**Status:** Approved

## Problem

All non-duplex voice modes (toggle output, walkie-talkie, hands-free) wait for the full LLM response before starting TTS synthesis. The entire text is sent as a single HTTP POST to `/api/voice/synthesize`, which returns one large WAV file. This creates 5-15s of silence between the user's message and the first audio playback.

Full-duplex mode already uses WebSocket streaming with chunked TTS but is isolated from the other modes.

## Solution

Unify all voice modes through the WebSocket streaming path (`/api/voice/stream`). Add a sentence accumulator that detects completed sentences during LLM streaming and dispatches each to TTS immediately. First audio plays within ~1.5-3s.

## Architecture

### Before (3 separate TTS paths)

```
Toggle mode:    content → wait for isTyping=false → speak() → HTTP POST full text → wait full WAV → play
Walkie/Hands:   content → wait for sendMessage() → speak() → HTTP POST full text → wait full WAV → play
Full-duplex:    content → WS "speak" → backend chunks & streams → playAudioChunk() queue → plays immediately
```

### After (1 unified path)

```
ALL modes:  streaming content → sentence accumulator → WS "speak_sentence" per sentence →
            backend synthesizes & streams tts_audio chunks → playAudioChunk() queue →
            first sentence plays while LLM is still generating
```

## Data Flow

```
LLM SSE stream:  "Hello. " → "Hello. I can help" → "Hello. I can help with that. " → ...
                      ↓                                        ↓
Accumulator:     sentence="Hello."                  sentence="I can help with that."
                      ↓                                        ↓
WS send:         {type:"speak_sentence",            {type:"speak_sentence",
                  text:"Hello."}                     text:"I can help with that."}
                      ↓                                        ↓
Backend queue:   synthesize("Hello.")               synthesize("I can help with that.")
                  → tts_audio chunk                   → tts_audio chunk
                      ↓                                        ↓
Frontend:        playAudioChunk() → PLAYING         playAudioChunk() → queued, plays next
```

## Component Changes

### 1. Backend: `voice_stream.py`

**New message type: `speak_sentence`**

Unlike the existing `speak` (which cancels active TTS for barge-in), `speak_sentence` queues for sequential playback:

```python
elif msg_type == "speak_sentence":
    text = msg.get("text", "").strip()
    voice_id = msg.get("voice_id", "")
    if text:
        await _sentence_queue.put((text, voice_id))
```

**New message type: `flush`**

Signals no more sentences coming — backend sends `tts_end` after queue drains:

```python
elif msg_type == "flush":
    await _sentence_queue.put(None)  # sentinel
```

**New: `_tts_queue_worker` coroutine**

Runs as a background task per connection, drains the sentence queue sequentially:

```python
async def _tts_queue_worker(ws, queue, cancel_event):
    while True:
        item = await queue.get()
        if item is None:  # flush sentinel
            await _send_json(ws, {"type": "tts_end"})
            continue
        text, voice_id = item
        if cancel_event.is_set():
            continue  # skip on barge-in
        wav_bytes = await tts.synthesize(text, voice_id=voice_id)
        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
        await _send_json(ws, {"type": "tts_audio", "data": audio_b64, "chunk": ..., "total": ...})
```

**Barge-in compatibility:** Existing `speak` and `barge_in` messages still cancel active TTS and clear the queue.

### 2. Frontend: `useVoiceOutput.ts`

**New: Lazy WS connection management**

- `_connectTtsWs()` — opens WS to `/api/voice/stream`, sets up `tts_audio` message handler that feeds `playAudioChunk()`
- `_disconnectTtsWs()` — closes after idle timeout (~30s)
- Connection opened lazily on first `speakStreaming()` call

**New: `speakStreaming(text: string)`**

Sends `speak_sentence` over WS. Falls back to HTTP `speak()` if WS unavailable.

**New: `flushStreaming()`**

Sends `flush` message to signal end of sentence stream.

**Existing `speak()` → fallback only**

Still available for when WS is down or for non-streaming callers.

### 3. Frontend: `ChatInterface.vue` watcher

Replace current "wait for isTyping=false" watcher with sentence accumulator:

```typescript
let _lastSpokenIdx = 0

watch(
  () => /* current speakable content from streaming */,
  (content) => {
    if (!voiceOutputEnabled.value || voiceConversation.isActive.value) return

    if (store.isTyping && content) {
      // During streaming: extract completed sentences
      const newText = content.slice(_lastSpokenIdx)
      const sentences = extractCompleteSentences(newText)
      for (const s of sentences) {
        speakStreaming(s)
        _lastSpokenIdx += s.length
      }
    } else if (!store.isTyping && content) {
      // Stream ended: flush remainder
      const remainder = content.slice(_lastSpokenIdx)
      if (remainder.trim()) speakStreaming(remainder)
      flushStreaming()
      _lastSpokenIdx = 0
    }
  }
)
```

The `_SPEAKABLE_TYPES` filter stays — only `response` and `message` types trigger TTS.

### 4. Frontend: `useVoiceConversation.ts`

Update `_dispatchTranscript()` to use `speakStreaming()` + `flushStreaming()` instead of `speak(speechText, true)`. This gives walkie-talkie and hands-free modes the same streaming TTS.

## Sentence Accumulator Logic

```typescript
function extractCompleteSentences(text: string): string[] {
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

- Splits on `. `, `! `, `? ` followed by whitespace
- Returns only COMPLETE sentences (text after last terminator stays buffered)
- Remainder flushed when streaming ends

## Error Handling

| Scenario | Handling |
|---|---|
| WS disconnects mid-stream | Fall back to HTTP `speak()` for remaining text |
| User sends new message while speaking | `barge_in` clears queue + stops audio |
| Very short response (< 1 sentence) | Flushed on stream end, single TTS call |
| Empty/tag-only response (thoughts) | `_SPEAKABLE_TYPES` filter prevents dispatch |
| WS fails to connect | Degrade to HTTP `speak()` silently |
| Backend TTS worker down | Error chunk logged, stops gracefully |
| Multiple rapid sentences | Backend queue processes sequentially |

## Files Changed

| File | Change |
|---|---|
| `autobot-backend/api/voice_stream.py` | `speak_sentence`, `flush`, `_tts_queue_worker` |
| `autobot-frontend/src/composables/useVoiceOutput.ts` | WS connection, `speakStreaming()`, `flushStreaming()` |
| `autobot-frontend/src/components/chat/ChatInterface.vue` | Sentence accumulator watcher |
| `autobot-frontend/src/composables/useVoiceConversation.ts` | `_dispatchTranscript()` uses streaming |

## Performance Target

- Before: ~5-15s time-to-first-audio
- After: ~1.5-3s time-to-first-audio (first sentence plays while LLM still generating)
