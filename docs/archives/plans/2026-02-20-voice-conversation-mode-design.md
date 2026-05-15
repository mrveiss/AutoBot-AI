# Voice Conversation Mode Design

**Date:** 2026-02-20
**Issues:** #1029 (Tier 1), #1030 (Tier 2), #1031 (Tier 3)
**Author:** mrveiss

## Problem

The chat page (`/chat`) has speech-to-text input (browser SpeechRecognition → text box dictation) and text-to-speech output (`useVoiceOutput.ts` → Kani-TTS-2), but no continuous conversation loop. Users must: tap mic → dictate → manually send → wait → hear response → manually tap mic again.

## Solution: Three-Tier Voice Conversation

### Tier 1: Walkie-Talkie (#1029) — Frontend Only

**Flow:** Tap mic → SpeechRecognition → tap again/silence → auto-send → AutoBot responds → TTS plays → ready for next tap.

**State machine:**
```
idle → listening → processing → speaking → idle
         ↑                                  |
         └──────────────────────────────────┘
```

**Components:**
- `useVoiceConversation.ts` — state machine, mode management, wraps existing `useVoiceOutput.speak()`
- `VoiceConversationOverlay.vue` — overlay panel with mic animation, transcript bubbles, mode selector
- `ChatInterface.vue` — new "Voice Chat" button in header

**Backend:** None needed. Uses existing `/api/voice/synthesize` and browser SpeechRecognition.

### Tier 2: Hands-Free (#1030) — Frontend + Backend

**Flow:** Activate once → VAD detects speech → MediaRecorder captures → server-side Whisper transcribes → auto-send → TTS → mic re-opens.

**New backend:** `POST /api/voice/transcribe` — accepts audio blob, returns text via Whisper.

**New frontend:** Browser-side VAD (Silero VAD ONNX/WASM), `MediaRecorder` capture, waveform visualization.

### Tier 3: Full-Duplex (#1031) — Frontend + Backend

**Flow:** WebSocket audio streaming, server-side VAD, barge-in (interrupt AutoBot mid-speech).

**New backend:** `WS /api/voice/stream` — bidirectional audio chunks.

**New frontend:** `AudioWorklet` capture, barge-in detection, streaming transcript display.

## UI Design

### Voice Chat Overlay

Activated from a button in the chat header. Slides up as a panel overlay on the chat view.

**Layout:**
```
┌─────────────────────────────────────┐
│  Voice Chat          [mode ▼]  [✕]  │
├─────────────────────────────────────┤
│                                     │
│  ┌─────────────────────────────┐    │
│  │  You: "What's the status    │    │
│  │  of the deployment?"        │    │
│  └─────────────────────────────┘    │
│                                     │
│      ┌─────────────────────────┐    │
│      │  AutoBot: "All services │    │
│      │  are healthy..."        │    │
│      └─────────────────────────┘    │
│                                     │
│           ┌──────────┐              │
│           │    🎤    │              │
│           │  (tap)   │              │
│           └──────────┘              │
│        Tap to speak                 │
└─────────────────────────────────────┘
```

**Mode selector dropdown:**
- Walkie-talkie (active)
- Hands-free (coming soon)
- Full-duplex (coming soon)

## Existing Infrastructure

| Component | Location | Purpose |
|-----------|----------|---------|
| `useVoiceOutput.ts` | `src/composables/` | TTS playback via `/api/voice/synthesize` |
| `ChatInput.vue` | `src/components/chat/` | Browser SpeechRecognition (dictation) |
| `ChatInterface.vue` | `src/components/chat/` | Volume toggle, auto-speak on response |
| `/api/voice/synthesize` | `api/voice.py` | Kani-TTS-2 WAV synthesis |
| `/api/voice/listen` | `api/voice.py` | Server-side STT |
| `AudioPipeline` | `media/audio/pipeline.py` | Whisper transcription |
| `tts_client.py` | `services/` | Async Kani-TTS-2 HTTP client |

## Implementation Order

1. **Tier 1** (this session): Walkie-talkie. Frontend only.
2. **Tier 2** (future): Hands-free. Add VAD + server transcribe endpoint.
3. **Tier 3** (future): Full-duplex. Add WebSocket streaming.
