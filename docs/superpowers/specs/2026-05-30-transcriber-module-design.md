# Transcriber Module — Design Spec
**Date:** 2026-05-30
**Author:** mrveiss
**Status:** Approved

---

## Overview

A general-purpose audio transcription module integrated into AutoBot as a self-contained extension. Handles any audio domain — meetings, interviews, podcasts, lectures — with speaker diarization, segment-level editing, AI analysis, multi-format export, and optional Knowledge Base push.

The module is **provider-agnostic**: language is detected automatically, speech providers are resolved from AutoBot's language-keyed speech provider registry. New languages are added by registering providers — the transcriber itself never changes.

---

## Architecture: A + C (Self-Contained Module + Extension Registration)

**Approach:** The transcriber is a fully self-contained Python package (`autobot-backend/transcriber/`) registered as an AutoBot builtin extension via `extensions/builtin/transcriber_extension.py`.

**Why A+C:**
- Self-contained (A) gives clear ownership boundary, isolated DB, fast implementation, easy testing
- Extension registration (C) gives clean enable/disable toggle, lifecycle hooks (startup/shutdown), route mounting through `feature_routers.py`
- Together: no duplication of job queue/SSE (wired to AutoBot's `async_work`), no indirection overhead (module is self-contained), clean toggle via `TRANSCRIBER_ENABLED` env var

---

## Module Structure

```
autobot-backend/
├── transcriber/
│   ├── __init__.py
│   ├── database.py                   # aiosqlite CRUD for transcriber.db sidecar
│   ├── models.py                     # Pydantic schemas (ProjectCreate, RecordingDetail, SegmentUpdate…)
│   ├── deps.py                       # get_db() dependency injection
│   ├── pipeline/
│   │   ├── queue.py                  # Job orchestrator — wired to AutoBot async_work
│   │   ├── transcribe.py             # Calls AutoBot speech provider interface only
│   │   ├── diarize.py                # Pyannote speaker diarization (lazy-load, CPU)
│   │   ├── merge.py                  # Align diarization timeline + transcript text → segments
│   │   ├── demucs.py                 # Optional source separation (user-toggled)
│   │   └── progress.py               # SSE progress events via AutoBot events/ bus
│   ├── routes/
│   │   ├── projects.py               # Project CRUD
│   │   ├── recordings.py             # Upload, list, delete, process, SSE, retry
│   │   ├── transcripts.py            # Segments, speakers, notes, KB push
│   │   ├── export.py                 # DOCX, PDF, SRT, VTT
│   │   └── ai.py                     # Streaming AI analysis → llm_shared
│   ├── export/
│   │   ├── docx_export.py
│   │   ├── pdf_export.py
│   │   ├── srt_export.py             # SubRip subtitle format
│   │   └── vtt_export.py             # WebVTT subtitle format
│   ├── ai/
│   │   ├── prompts.py                # General-purpose prompts (domain-agnostic)
│   │   └── context.py                # Transcript context builder for llm_shared
│   ├── knowledge/
│   │   └── kb_push.py                # Manual push → AutoBot DocIndexerService
│   └── tests/
│       └── ...                       # Full test suite (see Testing section)
│
├── extensions/builtin/
│   └── transcriber_extension.py      # Mount routes, lifecycle hooks, toggle
│
└── voice_processing/
    └── providers/                    # NEW — language-keyed speech provider registry
        ├── __init__.py               # Registry: {lang_code → [providers]}
        ├── lv/
        │   ├── late_provider.py      # Latvian — local LATE binary
        │   └── tilde_provider.py     # Latvian — Tilde cloud ASR
        └── en/
            └── ...                   # English providers (future)
```

---

## Provider Architecture

**Rule:** The transcriber has zero knowledge of specific providers. It calls only AutoBot's provider interfaces.

**Speech providers are language-keyed:**
```python
get_speech_provider(lang="lv")  # → LATE or Tilde, resolved from registry
get_speech_provider(lang="en")  # → registered English provider
```

**Provider registration flow:**
1. Extension startup registers all providers in `voice_processing/providers/<lang>/`
2. Pipeline detects language via `lingua-language-detector`
3. `transcribe.py` calls `get_speech_provider(lang=detected_lang)`
4. No provider for language → graceful error, user informed

**AI analysis:** calls `llm_shared` only — same as every other AutoBot module.

**LATE and Tilde are Latvian-specific providers** living in `voice_processing/providers/lv/`. Other languages get their own provider directories. Adding a new language requires zero changes to the transcriber module.

---

## Database Schema (SQLite Sidecar)

**Location:** `autobot-backend/data/transcriber/transcriber.db`

```sql
projects (
  id, name, description, created_at, user_id
)

recordings (
  id, project_id, filename, filepath, duration, status,
  speaker_count, process_seconds, engine_used, language_detected,
  uploaded_at, user_id
)

speakers (
  id, recording_id, label, display_name, language
)

segments (
  id, recording_id, speaker_id, start_time, end_time,
  text, original_text, is_edited, is_overlap
)

notes (
  id, segment_id, recording_id, content, created_at
)

kb_pushes (
  id, recording_id, kb_collection_id, pushed_at, pushed_by
)
```

**Key decisions:**
- Dedicated SQLite sidecar: pipeline batch writes get uncontested write access, no lock contention with AutoBot's main DB
- No `settings` table — API keys and provider config live in AutoBot's secrets manager
- `user_id` on `projects` and `recordings` — cross-referenced in memory, no cross-DB JOIN needed
- `kb_pushes` tracks manual push history per recording

**File storage:**
```
autobot-backend/data/transcriber/
├── uploads/      # Raw audio files
├── processed/    # Converted WAVs + chunks
└── exports/      # DOCX, PDF, SRT, VTT output
```

---

## Processing Pipeline

Seven sequential async stages, each firing SSE progress events via AutoBot's `events/` bus:

```
[1] FFmpeg conversion        raw audio → normalized WAV (16kHz mono)          10%
[2] Language detection       lingua-language-detector → provider lookup        15%
[3] Source separation        Demucs vocals isolation (optional, user-toggled)  25%
[4] Speaker diarization      Pyannote → who spoke when                         50%
[5] Transcription            AutoBot speech provider (language-matched)        80%
[6] Merge                    diarization timeline + transcript text → segments 90%
[7] Persist                  write speakers, segments to transcriber.db       100%
```

**Job queue:** wired to AutoBot's `async_work` infrastructure — no standalone asyncio queue.

**SSE progress:** fired through AutoBot's `events/` bus. Frontend subscribes to `GET /api/transcriber/recordings/{id}/progress`.

**Failure handling:** each stage records failure reason on the recording row. Partial results from earlier stages are preserved. User can retry from the failed stage via `POST /api/transcriber/recordings/{id}/retry`.

**Pyannote lazy-load:** model loaded on first use, held in memory, released on extension shutdown. Not pre-loaded at AutoBot boot.

---

## API Routes

All routes under `/api/transcriber/`, mounted via extension, protected by AutoBot's auth middleware.

```
Projects
  POST   /api/transcriber/projects
  GET    /api/transcriber/projects
  GET    /api/transcriber/projects/:id
  PATCH  /api/transcriber/projects/:id
  DELETE /api/transcriber/projects/:id          (cascade to recordings)

Recordings
  POST   /api/transcriber/projects/:id/recordings
  GET    /api/transcriber/projects/:id/recordings
  DELETE /api/transcriber/recordings/:id
  GET    /api/transcriber/recordings/:id/audio   (stream)
  GET    /api/transcriber/recordings/:id/progress  (SSE)
  POST   /api/transcriber/recordings/:id/retry

Transcripts
  GET    /api/transcriber/recordings/:id/transcript
  PATCH  /api/transcriber/segments/:id           (inline text edit)
  PATCH  /api/transcriber/speakers/:id           (rename display name)
  POST   /api/transcriber/segments/:id/notes
  PATCH  /api/transcriber/notes/:id
  DELETE /api/transcriber/notes/:id

Export
  POST   /api/transcriber/recordings/:id/export  {format: docx|pdf|srt|vtt, options}

AI Analysis
  POST   /api/transcriber/recordings/:id/ai/ask  (SSE streaming → llm_shared)

Knowledge Base
  POST   /api/transcriber/recordings/:id/kb/push
  GET    /api/transcriber/recordings/:id/kb/status
```

---

## Frontend (Vue 3 + TypeScript)

### Routes

```
/transcriber                                      TranscriberLayout.vue
/transcriber/projects                             ProjectsView.vue
/transcriber/projects/:id                         ProjectDetailView.vue
/transcriber/projects/:id/recordings/:recId       TranscriptView.vue
/documents                                        DocumentsView.vue (existing + TranscriberProjectsCard)
/settings                                         SettingsView.vue (existing + Transcriber section)
```

### Components

```
views/transcriber/
├── TranscriberLayout.vue       # Sidebar nav (Projects / Settings shortcut)
├── ProjectsView.vue            # Project grid/list, search, create modal
├── ProjectDetailView.vue       # Recordings list, upload modal, SSE progress bars
└── TranscriptView.vue          # Main transcript workspace

components/transcriber/
├── WaveformPlayer.vue          # WaveSurfer.js 7 wrapper
├── SegmentTable.vue            # Speaker | Timestamp | Text rows, inline edit
├── SpeakerLabel.vue            # Editable speaker display name
├── NotePopover.vue             # Per-segment notes create/edit/delete
├── AiAnalysisPanel.vue         # Slide-in: Summarize / Key Facts / Custom Q → SSE
├── ExportMenu.vue              # Dropdown: DOCX / PDF / SRT / VTT
├── KbPushButton.vue            # Push to KB + pushed status indicator
├── UploadModal.vue             # Drag-drop upload + progress
└── ProcessingProgress.vue      # SSE-driven pipeline stage progress bar

composables/transcriber/
├── useTranscriberApi.ts        # Typed API client via AutoBot useApi()
├── useWaveform.ts              # WaveSurfer lifecycle + segment seek sync
└── useSseProgress.ts           # SSE subscription → reactive progress state

stores/transcriber/
└── useTranscriberStore.ts      # Pinia: active project, recording, segments, speakers
```

### AutoBot design integration
- AutoBot design tokens, component library, CSS variables throughout — no custom theme
- Nav entry added to `navItems` config, conditionally shown when `TRANSCRIBER_ENABLED`
- All HTTP calls via `useApi()` from AutoBot's ApiClient — no raw fetch
- All logging via `createLogger('Transcriber')` — no `console.*`
- Pinia store follows AutoBot's existing store conventions

---

## Export Formats

| Format | Content | Use case |
|--------|---------|----------|
| DOCX   | Speaker colors, timestamps, text, notes | Formal records, legal |
| PDF    | Same as DOCX via HTML→WeasyPrint | Sharing, archiving |
| SRT    | `start --> end\nSpeaker: text` blocks | Video subtitling, media players |
| VTT    | WebVTT — `<track>` compatible | Web players, accessibility |

SRT and VTT are direct string formatting from segment rows — no external dependencies.

---

## Knowledge Base Push

Manual per-recording action. Flow:

1. User clicks "Push to KB" on `TranscriptView`
2. `kb_push.py` fetches all segments for that recording
3. Formats each segment: `"[Speaker Name, HH:MM:SS] text"`
4. Calls AutoBot's `DocIndexerService` with user-selected or default collection
5. Records push in `kb_pushes` table (recording_id, collection_id, pushed_at, pushed_by)
6. `KbPushButton.vue` shows pushed status + timestamp, "Re-index" option if already pushed

Not every recording should go to KB — this is intentionally manual.

---

## Extension Lifecycle

`extensions/builtin/transcriber_extension.py`:

**Startup:**
- Register LATE + Tilde into `voice_processing/providers/lv/`
- Register any other language providers found in `voice_processing/providers/`
- Open `transcriber.db` aiosqlite connection
- Wire job queue to `async_work`
- Do NOT pre-load Pyannote (lazy on first use)

**Shutdown:**
- Drain in-flight pipeline jobs
- Close DB connection pool
- Release Pyannote model from memory

**Toggle:** `TRANSCRIBER_ENABLED=true` (env var, via `autobot_shared.ssot_config`). When false: routes not mounted, nav entry hidden.

---

## Testing

```
transcriber/tests/
├── test_database.py
├── test_projects_api.py
├── test_recordings_api.py
├── test_transcripts_api.py
├── test_export_docx.py
├── test_export_pdf.py
├── test_export_srt.py          # New
├── test_export_vtt.py          # New
├── test_pipeline_queue.py
├── test_pipeline_transcribe.py
├── test_pipeline_diarize.py
├── test_pipeline_merge.py
├── test_pipeline_demucs.py
├── test_kb_push.py             # New
├── test_ai_analysis.py
└── test_extension.py           # Extension lifecycle (startup/shutdown)
```

Uses AutoBot's test fixtures. No standalone test DB setup.

---

## AutoBot Conventions Checklist

- `from autobot_shared.redis_client import get_redis_client` for any Redis use
- `from autobot_shared.ssot_config import config` for all config
- `logging.getLogger(__name__)` backend / `createLogger('Transcriber')` frontend
- No `print()` or `console.*` anywhere
- `encoding='utf-8'` on all file I/O
- All I/O async — no sync calls in async paths
- Functions ≤ 30 lines
- Routes registered via `feature_routers.py` through extension
- Copyright header on every file: `# Copyright (c) 2025 mrveiss`
