---
tags:
  - api
  - transcriber
---

# Transcript Analysis & KB Push API

Endpoints served by `autobot-backend/api/transcripts.py` (MVA-2176, wired in via #9863).
They operate on transcriber recordings (GH#9044) — `{transcript_id}` is the numeric
recording id from the transcriber module.

## WebSocket: streaming AI analysis

```
wss://<host>/api/transcripts/{transcript_id}/analyze?token=<jwt>
```

1. Connect with a valid JWT (`token` query parameter; single-user mode bypasses auth
   like all other WebSocket endpoints).
2. Send one JSON request:
   ```json
   {"analysis_type": "summarize", "custom_prompt": null, "context": null}
   ```
   `analysis_type`: `summarize` | `key_facts` | `protocol` | `custom`
   (`custom` requires `custom_prompt`).
3. The server streams analysis text chunks built from the recording's stored
   segments and speakers, then closes the connection.

Close codes: `4001` unauthorized · `4004` recording not found / not owned ·
`1008` recording not yet transcribed or invalid request · `1011` internal error.

## POST `/api/transcripts/{transcript_id}/kb-push`

Pushes a single transcript segment into the main Knowledge Base (per-segment
granularity; for whole-recording push use
`POST /api/transcriber/recordings/{id}/kb/push`).

Request body (`TranscriptKBPushRequest`):

| Field | Type | Notes |
| --- | --- | --- |
| `segment_text` | string (required) | Segment text, max 50 000 chars |
| `segment_start` / `segment_end` | float | Segment timing in seconds |
| `speaker` | string | Speaker name |
| `confidence` | float 0–1 | Transcription confidence |
| `language` | string | Language code |

Response (`TranscriptKBPushResponse`): `{ success, doc_id, message }`.

Errors: `404` unknown/foreign recording id · `503` transcriber storage unavailable
(`TRANSCRIBER_ENABLED != true` or init failure).

KB metadata is system-controlled: `source_type=transcript`,
`transcript_id`, `source=transcript:{id}`, `verification_status=unverified`,
`user_id` of the caller. Client-supplied fields cannot override these.
