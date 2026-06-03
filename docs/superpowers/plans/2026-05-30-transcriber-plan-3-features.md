# Transcriber Module — Plan 3: Transcript Features

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete backend feature set — transcript viewing/editing (segments, speakers, notes), streaming AI analysis via `llm_shared`, four export formats (DOCX, PDF, SRT, VTT), and manual Knowledge Base push.

**Architecture:** All routes extend `autobot-backend/transcriber/routes/`. AI analysis calls AutoBot's `llm_shared` providers exclusively. Export is pure transcriber-internal (DOCX via python-docx, PDF via WeasyPrint, SRT/VTT as string formatting). KB push calls AutoBot's `knowledge/connectors/` framework.

**Tech Stack:** Python 3.11+, FastAPI SSE, python-docx, WeasyPrint, autobot llm_shared, autobot knowledge connectors

**Prerequisite:** Plan 2 complete.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `autobot-backend/transcriber/routes/transcripts.py` | Segments, speakers, notes CRUD |
| Create | `autobot-backend/transcriber/routes/export.py` | Export endpoint (DOCX/PDF/SRT/VTT) |
| Create | `autobot-backend/transcriber/routes/ai.py` | Streaming AI analysis → llm_shared |
| Create | `autobot-backend/transcriber/routes/kb.py` | KB push + status |
| Create | `autobot-backend/transcriber/export/__init__.py` | Export package |
| Create | `autobot-backend/transcriber/export/docx_export.py` | Word document generation |
| Create | `autobot-backend/transcriber/export/pdf_export.py` | HTML→PDF via WeasyPrint |
| Create | `autobot-backend/transcriber/export/srt_export.py` | SubRip subtitle format |
| Create | `autobot-backend/transcriber/export/vtt_export.py` | WebVTT subtitle format |
| Create | `autobot-backend/transcriber/ai/__init__.py` | AI package |
| Create | `autobot-backend/transcriber/ai/prompts.py` | Domain-agnostic analysis prompts |
| Create | `autobot-backend/transcriber/ai/context.py` | Transcript context builder |
| Create | `autobot-backend/transcriber/knowledge/__init__.py` | Knowledge package |
| Create | `autobot-backend/transcriber/knowledge/kb_push.py` | Push segments → DocIndexerService |
| Modify | `autobot-backend/transcriber/database.py` | Add notes + kb_pushes CRUD |
| Modify | `autobot-backend/extensions/builtin/transcriber_extension.py` | Include new routes |
| Create | `autobot-backend/transcriber/tests/test_transcripts_api.py` | Transcript route tests |
| Create | `autobot-backend/transcriber/tests/test_export_srt.py` | SRT tests |
| Create | `autobot-backend/transcriber/tests/test_export_vtt.py` | VTT tests |
| Create | `autobot-backend/transcriber/tests/test_export_docx.py` | DOCX tests |
| Create | `autobot-backend/transcriber/tests/test_kb_push.py` | KB push tests |
| Create | `autobot-backend/transcriber/tests/test_ai_analysis.py` | AI route tests |

---

### Task 1: Transcript routes (segments, speakers, notes)

**Files:**
- Create: `autobot-backend/transcriber/routes/transcripts.py`
- Modify: `autobot-backend/transcriber/database.py`
- Create: `autobot-backend/transcriber/tests/test_transcripts_api.py`

- [ ] **Step 1: Add notes + KB push CRUD to database.py**

Append to [autobot-backend/transcriber/database.py](autobot-backend/transcriber/database.py):

```python
    # ── Notes ─────────────────────────────────────────────────────────────────

    async def create_note(self, segment_id: int, recording_id: int, content: str) -> int:
        cur = await self._conn.execute(
            "INSERT INTO notes (segment_id, recording_id, content) VALUES (?,?,?)",
            (segment_id, recording_id, content),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_note(self, note_id: int) -> dict | None:
        cur = await self._conn.execute("SELECT * FROM notes WHERE id=?", (note_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_notes(self, recording_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM notes WHERE recording_id=? ORDER BY created_at", (recording_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_note(self, note_id: int, content: str) -> None:
        await self._conn.execute("UPDATE notes SET content=? WHERE id=?", (content, note_id))
        await self._conn.commit()

    async def delete_note(self, note_id: int) -> None:
        await self._conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
        await self._conn.commit()

    # ── KB Pushes ─────────────────────────────────────────────────────────────

    async def create_kb_push(
        self, recording_id: int, kb_collection_id: str, pushed_by: str
    ) -> int:
        cur = await self._conn.execute(
            "INSERT INTO kb_pushes (recording_id, kb_collection_id, pushed_by) VALUES (?,?,?)",
            (recording_id, kb_collection_id, pushed_by),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_latest_kb_push(self, recording_id: int) -> dict | None:
        cur = await self._conn.execute(
            "SELECT * FROM kb_pushes WHERE recording_id=? ORDER BY pushed_at DESC LIMIT 1",
            (recording_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
```

- [ ] **Step 2: Write failing tests for transcript routes**

```python
# autobot-backend/transcriber/tests/test_transcripts_api.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from transcriber.routes.transcripts import router
from transcriber.database import Database
from transcriber.deps import get_db


@pytest.fixture
def app_with_data(tmp_path):
    a = FastAPI()
    db = Database(str(tmp_path / "test.db"))

    async def override():
        return db

    a.dependency_overrides[get_db] = override
    a.include_router(router, prefix="/api/transcriber")

    @a.on_event("startup")
    async def startup():
        await db.connect()
        pid = await db.create_project("P", "", "u1")
        rid = await db.create_recording(pid, "a.wav", "/tmp/a.wav", "u1")
        sid = await db.create_speaker(rid, "SPEAKER_00", "Alice", "lv")
        await db.create_segment(rid, sid, 0.0, 1.5, "Hello world")
        a.state._test_rid = rid
        a.state._test_sid = sid

    return a


@pytest.mark.asyncio
async def test_get_transcript(app_with_data):
    async with AsyncClient(transport=ASGITransport(app=app_with_data), base_url="http://test") as c:
        await app_with_data.router.startup()
        rid = app_with_data.state._test_rid
        r = await c.get(f"/api/transcriber/recordings/{rid}/transcript")
        assert r.status_code == 200
        data = r.json()
        assert len(data["segments"]) == 1
        assert data["segments"][0]["text"] == "Hello world"
        assert data["speakers"][0]["display_name"] == "Alice"


@pytest.mark.asyncio
async def test_update_segment_text(app_with_data):
    async with AsyncClient(transport=ASGITransport(app=app_with_data), base_url="http://test") as c:
        await app_with_data.router.startup()
        rid = app_with_data.state._test_rid
        transcript = (await c.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
        seg_id = transcript["segments"][0]["id"]
        r = await c.patch(f"/api/transcriber/segments/{seg_id}", json={"text": "Updated text"})
        assert r.status_code == 200
        assert r.json()["is_edited"] is True
        assert r.json()["text"] == "Updated text"


@pytest.mark.asyncio
async def test_rename_speaker(app_with_data):
    async with AsyncClient(transport=ASGITransport(app=app_with_data), base_url="http://test") as c:
        await app_with_data.router.startup()
        sid = app_with_data.state._test_sid
        r = await c.patch(f"/api/transcriber/speakers/{sid}", json={"display_name": "Bob"})
        assert r.status_code == 200
        assert r.json()["display_name"] == "Bob"


@pytest.mark.asyncio
async def test_create_and_delete_note(app_with_data):
    async with AsyncClient(transport=ASGITransport(app=app_with_data), base_url="http://test") as c:
        await app_with_data.router.startup()
        rid = app_with_data.state._test_rid
        transcript = (await c.get(f"/api/transcriber/recordings/{rid}/transcript")).json()
        seg_id = transcript["segments"][0]["id"]
        r = await c.post(f"/api/transcriber/segments/{seg_id}/notes",
                         json={"content": "Important!", "recording_id": rid})
        assert r.status_code == 201
        note_id = r.json()["id"]
        r2 = await c.delete(f"/api/transcriber/notes/{note_id}")
        assert r2.status_code == 204
```

- [ ] **Step 3: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_transcripts_api.py -v
```
Expected: `ModuleNotFoundError: No module named 'transcriber.routes.transcripts'`

- [ ] **Step 4: Implement transcript routes**

```python
# autobot-backend/transcriber/routes/transcripts.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Transcript routes: segments, speakers, notes."""
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import (
    NoteCreate, NoteOut, NoteUpdate, SegmentOut, SegmentUpdate,
    SpeakerOut, SpeakerUpdate, TranscriptOut, RecordingOut,
)

router = APIRouter(tags=["transcriber-transcripts"])


@router.get("/recordings/{recording_id}/transcript", response_model=TranscriptOut)
async def get_transcript(recording_id: int, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    speakers = await db.list_speakers(recording_id)
    segments = await db.list_segments(recording_id)
    return TranscriptOut(
        recording=RecordingOut(**rec),
        speakers=[SpeakerOut(**s) for s in speakers],
        segments=[SegmentOut(**s) for s in segments],
    )


@router.patch("/segments/{segment_id}", response_model=SegmentOut)
async def update_segment(segment_id: int, body: SegmentUpdate, db: Database = Depends(get_db)):
    cur = await db._conn.execute("SELECT * FROM segments WHERE id=?", (segment_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Segment not found")
    await db.update_segment_text(segment_id, body.text)
    cur2 = await db._conn.execute("SELECT * FROM segments WHERE id=?", (segment_id,))
    updated = await cur2.fetchone()
    return SegmentOut(**dict(updated))


@router.patch("/speakers/{speaker_id}", response_model=SpeakerOut)
async def update_speaker(speaker_id: int, body: SpeakerUpdate, db: Database = Depends(get_db)):
    cur = await db._conn.execute("SELECT * FROM speakers WHERE id=?", (speaker_id,))
    row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Speaker not found")
    await db.update_speaker(speaker_id, body.display_name)
    cur2 = await db._conn.execute("SELECT * FROM speakers WHERE id=?", (speaker_id,))
    updated = await cur2.fetchone()
    return SpeakerOut(**dict(updated))


@router.post("/segments/{segment_id}/notes", response_model=NoteOut, status_code=201)
async def create_note(segment_id: int, body: NoteCreate, request: Request, db: Database = Depends(get_db)):
    seg_cur = await db._conn.execute("SELECT recording_id FROM segments WHERE id=?", (segment_id,))
    seg_row = await seg_cur.fetchone()
    if not seg_row:
        raise HTTPException(404, "Segment not found")
    recording_id = seg_row[0]
    nid = await db.create_note(segment_id, recording_id, body.content)
    note = await db.get_note(nid)
    return NoteOut(**note)


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def update_note(note_id: int, body: NoteUpdate, db: Database = Depends(get_db)):
    if not await db.get_note(note_id):
        raise HTTPException(404, "Note not found")
    await db.update_note(note_id, body.content)
    return NoteOut(**await db.get_note(note_id))


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: int, db: Database = Depends(get_db)):
    if not await db.get_note(note_id):
        raise HTTPException(404, "Note not found")
    await db.delete_note(note_id)
    return Response(status_code=204)
```

- [ ] **Step 5: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_transcripts_api.py -v
```
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/transcriber/routes/transcripts.py \
        autobot-backend/transcriber/database.py \
        autobot-backend/transcriber/tests/test_transcripts_api.py
git commit -m "feat(transcriber): add transcript, segment, speaker, and notes routes"
```

---

### Task 2: SRT and VTT export

**Files:**
- Create: `autobot-backend/transcriber/export/__init__.py`
- Create: `autobot-backend/transcriber/export/srt_export.py`
- Create: `autobot-backend/transcriber/export/vtt_export.py`
- Create: `autobot-backend/transcriber/tests/test_export_srt.py`
- Create: `autobot-backend/transcriber/tests/test_export_vtt.py`

- [ ] **Step 1: Write failing tests**

```python
# autobot-backend/transcriber/tests/test_export_srt.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
from transcriber.export.srt_export import segments_to_srt


def test_srt_basic_format():
    segments = [
        {"start": 0.0, "end": 1.5, "text": "Hello", "speaker": "Alice"},
        {"start": 1.5, "end": 3.0, "text": "World", "speaker": "Bob"},
    ]
    result = segments_to_srt(segments, include_speaker=True)
    assert "00:00:00,000 --> 00:00:01,500" in result
    assert "Alice: Hello" in result
    assert "2\n" in result


def test_srt_without_speaker():
    segments = [{"start": 0.0, "end": 1.0, "text": "Hi", "speaker": "Alice"}]
    result = segments_to_srt(segments, include_speaker=False)
    assert "Alice" not in result
    assert "Hi" in result


def test_srt_empty():
    assert segments_to_srt([], include_speaker=True) == ""
```

```python
# autobot-backend/transcriber/tests/test_export_vtt.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
from transcriber.export.vtt_export import segments_to_vtt


def test_vtt_starts_with_webvtt():
    segments = [{"start": 0.0, "end": 1.0, "text": "Hello", "speaker": "Alice"}]
    result = segments_to_vtt(segments, include_speaker=True)
    assert result.startswith("WEBVTT")


def test_vtt_timestamp_format():
    segments = [{"start": 65.5, "end": 70.123, "text": "Test", "speaker": "Bob"}]
    result = segments_to_vtt(segments, include_speaker=False)
    assert "00:01:05.500 --> 00:01:10.123" in result
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_export_srt.py transcriber/tests/test_export_vtt.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement SRT and VTT**

```python
# autobot-backend/transcriber/export/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

```python
# autobot-backend/transcriber/export/srt_export.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Export transcript segments to SubRip (.srt) format."""


def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list[dict], *, include_speaker: bool = True) -> str:
    if not segments:
        return ""
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _fmt_srt_time(seg["start"])
        end = _fmt_srt_time(seg["end"])
        text = f"{seg['speaker']}: {seg['text']}" if include_speaker else seg["text"]
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)
```

```python
# autobot-backend/transcriber/export/vtt_export.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Export transcript segments to WebVTT (.vtt) format."""


def _fmt_vtt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def segments_to_vtt(segments: list[dict], *, include_speaker: bool = True) -> str:
    lines = ["WEBVTT", ""]
    for seg in segments:
        start = _fmt_vtt_time(seg["start"])
        end = _fmt_vtt_time(seg["end"])
        text = f"{seg['speaker']}: {seg['text']}" if include_speaker else seg["text"]
        lines.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_export_srt.py transcriber/tests/test_export_vtt.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/transcriber/export/ \
        autobot-backend/transcriber/tests/test_export_srt.py \
        autobot-backend/transcriber/tests/test_export_vtt.py
git commit -m "feat(transcriber/export): add SRT and VTT subtitle export"
```

---

### Task 3: DOCX and PDF export

**Files:**
- Create: `autobot-backend/transcriber/export/docx_export.py`
- Create: `autobot-backend/transcriber/export/pdf_export.py`
- Create: `autobot-backend/transcriber/tests/test_export_docx.py`
- Create: `autobot-backend/transcriber/routes/export.py`

- [ ] **Step 1: Write failing tests**

```python
# autobot-backend/transcriber/tests/test_export_docx.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from transcriber.export.docx_export import build_docx


def test_build_docx_returns_bytes():
    segments = [
        {"start": 0.0, "end": 1.5, "text": "Hello", "speaker_name": "Alice", "notes": []},
    ]
    result = build_docx(
        title="Test Recording",
        segments=segments,
        include_timestamps=True,
        include_notes=True,
        include_speaker_names=True,
    )
    assert isinstance(result, bytes)
    # DOCX files start with PK (zip magic bytes)
    assert result[:2] == b"PK"


def test_build_docx_without_timestamps():
    segments = [{"start": 0.0, "end": 1.0, "text": "Hi", "speaker_name": "Bob", "notes": []}]
    result = build_docx(
        title="Test",
        segments=segments,
        include_timestamps=False,
        include_notes=False,
        include_speaker_names=True,
    )
    assert isinstance(result, bytes)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_export_docx.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement DOCX export**

```python
# autobot-backend/transcriber/export/docx_export.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Export transcript to Word (.docx) format using python-docx."""
import io
from docx import Document
from docx.shared import Pt, RGBColor

_SPEAKER_COLORS = [
    RGBColor(0x1A, 0x73, 0xE8),
    RGBColor(0xD9, 0x34, 0x25),
    RGBColor(0x18, 0x8A, 0x38),
    RGBColor(0xFB, 0xBC, 0x04),
    RGBColor(0x8A, 0x2B, 0xE2),
]

def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_docx(
    title: str,
    segments: list[dict],
    *,
    include_timestamps: bool,
    include_notes: bool,
    include_speaker_names: bool,
) -> bytes:
    doc = Document()
    doc.add_heading(title, level=1)
    speaker_index: dict[str, int] = {}
    for seg in segments:
        speaker = seg.get("speaker_name", "Unknown")
        if speaker not in speaker_index:
            speaker_index[speaker] = len(speaker_index)
        color = _SPEAKER_COLORS[speaker_index[speaker] % len(_SPEAKER_COLORS)]
        p = doc.add_paragraph()
        if include_speaker_names:
            run = p.add_run(f"{speaker}")
            run.bold = True
            run.font.color.rgb = color
            p.add_run("  ")
        if include_timestamps:
            p.add_run(f"[{_fmt_ts(seg['start'])} → {_fmt_ts(seg['end'])}]  ").italic = True
        p.add_run(seg["text"])
        if include_notes and seg.get("notes"):
            for note in seg["notes"]:
                np = doc.add_paragraph(style="Quote")
                np.add_run(f"📝 {note['content']}")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Implement PDF export**

```python
# autobot-backend/transcriber/export/pdf_export.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Export transcript to PDF via HTML→WeasyPrint."""
import html as html_lib
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_SPEAKER_COLORS = ["#1a73e8", "#d93425", "#188a38", "#fbbc04", "#8a2be2"]

def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_pdf(
    title: str,
    segments: list[dict],
    *,
    include_timestamps: bool,
    include_notes: bool,
    include_speaker_names: bool,
) -> bytes:
    from weasyprint import HTML
    speaker_index: dict[str, int] = {}
    rows = []
    for seg in segments:
        speaker = seg.get("speaker_name", "Unknown")
        if speaker not in speaker_index:
            speaker_index[speaker] = len(speaker_index)
        color = _SPEAKER_COLORS[speaker_index[speaker] % len(_SPEAKER_COLORS)]
        ts = f'<span class="ts">[{_fmt_ts(seg["start"])} → {_fmt_ts(seg["end"])}]</span> ' if include_timestamps else ""
        spk = f'<span class="speaker" style="color:{color}">{html_lib.escape(speaker)}</span> ' if include_speaker_names else ""
        notes_html = ""
        if include_notes and seg.get("notes"):
            items = "".join(f'<li>{html_lib.escape(n["content"])}</li>' for n in seg["notes"])
            notes_html = f'<ul class="notes">{items}</ul>'
        rows.append(f'<p>{spk}{ts}{html_lib.escape(seg["text"])}{notes_html}</p>')

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{font-family: sans-serif; font-size: 11pt; margin: 2cm;}}
  h1 {{font-size: 16pt;}}
  .speaker {{font-weight: bold;}}
  .ts {{font-style: italic; color: #666; font-size: 9pt;}}
  .notes {{color: #555; font-size: 9pt; margin: 2px 0 6px 1em;}}
</style></head>
<body><h1>{html_lib.escape(title)}</h1>
{"".join(rows)}
</body></html>"""
    return HTML(string=html).write_pdf()
```

- [ ] **Step 5: Implement export route**

```python
# autobot-backend/transcriber/routes/export.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Export route — DOCX, PDF, SRT, VTT."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import ExportRequest

router = APIRouter(tags=["transcriber-export"])

_MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "srt": "text/plain; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
}
_EXT = {"docx": "docx", "pdf": "pdf", "srt": "srt", "vtt": "vtt"}


async def _build_segment_list(recording_id: int, db: Database) -> list[dict]:
    speakers = {s["id"]: s for s in await db.list_speakers(recording_id)}
    segments = await db.list_segments(recording_id)
    notes = await db.list_notes(recording_id)
    notes_by_seg: dict[int, list] = {}
    for n in notes:
        notes_by_seg.setdefault(n["segment_id"], []).append(n)
    result = []
    for seg in segments:
        spk = speakers.get(seg["speaker_id"], {})
        result.append({
            **seg,
            "speaker_name": spk.get("display_name", "Unknown"),
            "notes": notes_by_seg.get(seg["id"], []),
        })
    return result


@router.post("/recordings/{recording_id}/export")
async def export_recording(
    recording_id: int, body: ExportRequest, db: Database = Depends(get_db)
):
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    segments = await _build_segment_list(recording_id, db)
    title = rec["filename"]
    fmt = body.format

    if fmt == "srt":
        from transcriber.export.srt_export import segments_to_srt
        content = segments_to_srt(segments, include_speaker=body.include_speaker_names).encode("utf-8")
    elif fmt == "vtt":
        from transcriber.export.vtt_export import segments_to_vtt
        content = segments_to_vtt(segments, include_speaker=body.include_speaker_names).encode("utf-8")
    elif fmt == "docx":
        from transcriber.export.docx_export import build_docx
        content = build_docx(
            title, segments,
            include_timestamps=body.include_timestamps,
            include_notes=body.include_notes,
            include_speaker_names=body.include_speaker_names,
        )
    elif fmt == "pdf":
        from transcriber.export.pdf_export import build_pdf
        content = build_pdf(
            title, segments,
            include_timestamps=body.include_timestamps,
            include_notes=body.include_notes,
            include_speaker_names=body.include_speaker_names,
        )
    else:
        raise HTTPException(400, f"Unknown format: {fmt}")

    filename = f"{title}.{_EXT[fmt]}"
    return Response(
        content=content,
        media_type=_MIME[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 6: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_export_docx.py -v
```
Expected: 2 PASSED

- [ ] **Step 7: Commit**

```bash
git add autobot-backend/transcriber/export/ \
        autobot-backend/transcriber/routes/export.py \
        autobot-backend/transcriber/tests/test_export_docx.py
git commit -m "feat(transcriber/export): add DOCX, PDF, SRT, VTT export routes"
```

---

### Task 4: AI analysis (streaming SSE)

**Files:**
- Create: `autobot-backend/transcriber/ai/__init__.py`
- Create: `autobot-backend/transcriber/ai/prompts.py`
- Create: `autobot-backend/transcriber/ai/context.py`
- Create: `autobot-backend/transcriber/routes/ai.py`
- Create: `autobot-backend/transcriber/tests/test_ai_analysis.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_ai_analysis.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from transcriber.ai.context import build_context
from transcriber.ai.prompts import get_system_prompt


def test_build_context_formats_segments():
    segments = [
        {"start": 0.0, "end": 1.5, "speaker_name": "Alice", "text": "Hello"},
        {"start": 1.5, "end": 3.0, "speaker_name": "Bob", "text": "World"},
    ]
    ctx = build_context(segments, max_chars=5000)
    assert "Alice" in ctx
    assert "Hello" in ctx
    assert "00:00:00" in ctx


def test_build_context_truncates_at_max():
    segments = [{"start": float(i), "end": float(i+1), "speaker_name": "A", "text": "X" * 100}
                for i in range(200)]
    ctx = build_context(segments, max_chars=500)
    assert len(ctx) <= 600  # some slack for truncation message


def test_get_system_prompt_summarize():
    p = get_system_prompt("summarize")
    assert len(p) > 20


def test_get_system_prompt_custom():
    p = get_system_prompt("custom", custom_question="What was agreed?")
    assert "What was agreed?" in p
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_ai_analysis.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement AI context and prompts**

```python
# autobot-backend/transcriber/ai/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

```python
# autobot-backend/transcriber/ai/prompts.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Domain-agnostic analysis prompts for the transcriber module."""

_PROMPTS = {
    "summarize": (
        "You are an expert analyst. Read the following transcript and write a concise, "
        "structured summary covering the main topics discussed, decisions made, and action items. "
        "Be factual. Use bullet points for clarity."
    ),
    "key_facts": (
        "You are an expert analyst. Extract the key facts, figures, names, dates, and decisions "
        "from the following transcript. Present them as a numbered list."
    ),
    "protocol": (
        "You are an expert secretary. Draft a formal meeting protocol from the following transcript. "
        "Include: attendees (by speaker label), agenda items discussed, decisions made, "
        "action items with responsible parties. Be formal and precise."
    ),
}


def get_system_prompt(action: str, *, custom_question: str | None = None) -> str:
    if action == "custom":
        q = custom_question or "Analyze this transcript."
        return (
            f"You are an expert analyst. Answer the following question about the transcript: {q}\n"
            "Be concise and factual. Reference specific speakers and timestamps where relevant."
        )
    return _PROMPTS.get(action, _PROMPTS["summarize"])
```

```python
# autobot-backend/transcriber/ai/context.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Build transcript context string for LLM analysis."""


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_context(segments: list[dict], *, max_chars: int = 30_000) -> str:
    lines = []
    total = 0
    for seg in segments:
        line = f"[{seg['speaker_name']}, {_fmt_ts(seg['start'])}] {seg['text']}"
        if total + len(line) > max_chars:
            lines.append(f"\n... (transcript truncated at {max_chars} characters)")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)
```

- [ ] **Step 4: Implement AI route**

```python
# autobot-backend/transcriber/routes/ai.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Streaming AI analysis route — delegates to AutoBot llm_shared."""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import AiAskRequest
from transcriber.ai.prompts import get_system_prompt
from transcriber.ai.context import build_context
from transcriber.routes.export import _build_segment_list
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["transcriber-ai"])


@router.post("/recordings/{recording_id}/ai/ask")
async def ai_ask(
    recording_id: int,
    body: AiAskRequest,
    db: Database = Depends(get_db),
):
    if not await db.get_recording(recording_id):
        raise HTTPException(404, "Recording not found")
    segments = await _build_segment_list(recording_id, db)
    context = build_context(segments)
    system_prompt = get_system_prompt(body.action, custom_question=body.custom_question)

    async def stream():
        try:
            from llm_shared.providers import get_default_provider
            provider = get_default_provider()
            async for chunk in provider.stream_chat(
                system=system_prompt,
                user=f"Transcript:\n\n{context}",
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
        except Exception as exc:
            logger.exception("AI analysis failed for recording=%s", recording_id)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
```

- [ ] **Step 5: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_ai_analysis.py -v
```
Expected: 4 PASSED

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/transcriber/ai/ \
        autobot-backend/transcriber/routes/ai.py \
        autobot-backend/transcriber/tests/test_ai_analysis.py
git commit -m "feat(transcriber/ai): add streaming AI analysis via llm_shared"
```

---

### Task 5: Knowledge Base push

**Files:**
- Create: `autobot-backend/transcriber/knowledge/__init__.py`
- Create: `autobot-backend/transcriber/knowledge/kb_push.py`
- Create: `autobot-backend/transcriber/routes/kb.py`
- Create: `autobot-backend/transcriber/tests/test_kb_push.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_kb_push.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from unittest.mock import AsyncMock, patch
from transcriber.knowledge.kb_push import push_to_kb


@pytest.mark.asyncio
async def test_push_to_kb_formats_documents():
    segments = [
        {"start": 0.0, "end": 1.5, "speaker_name": "Alice", "text": "Hello world", "notes": []},
        {"start": 1.5, "end": 3.0, "speaker_name": "Bob", "text": "Goodbye", "notes": []},
    ]
    mock_indexer = AsyncMock()
    mock_indexer.add_documents = AsyncMock(return_value={"indexed": 2})
    with patch("transcriber.knowledge.kb_push._get_indexer", return_value=mock_indexer):
        result = await push_to_kb(
            recording_id=1,
            recording_filename="meeting.wav",
            segments=segments,
            collection_id="my-kb",
            pushed_by="u1",
        )
    assert result["indexed"] == 2
    call_args = mock_indexer.add_documents.call_args
    docs = call_args.kwargs.get("documents") or call_args.args[0]
    assert len(docs) == 2
    assert "Alice" in docs[0]["content"]
    assert "00:00:00" in docs[0]["content"]


@pytest.mark.asyncio
async def test_push_to_kb_returns_count():
    segments = [{"start": 0.0, "end": 1.0, "speaker_name": "A", "text": "Hi", "notes": []}]
    mock_indexer = AsyncMock()
    mock_indexer.add_documents = AsyncMock(return_value={"indexed": 1})
    with patch("transcriber.knowledge.kb_push._get_indexer", return_value=mock_indexer):
        result = await push_to_kb(1, "test.wav", segments, "col", "u1")
    assert result["indexed"] == 1
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_kb_push.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement KB push**

```python
# autobot-backend/transcriber/knowledge/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

```python
# autobot-backend/transcriber/knowledge/kb_push.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Manual Knowledge Base push — formats transcript segments as KB documents."""
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _fmt_ts(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _get_indexer():
    from knowledge.documents import DocIndexerService
    return DocIndexerService()


async def push_to_kb(
    recording_id: int,
    recording_filename: str,
    segments: list[dict],
    collection_id: str,
    pushed_by: str,
) -> dict:
    """Push all segments as documents to the AutoBot Knowledge Base.

    Each segment becomes one document: '[Speaker, HH:MM:SS] text'
    Returns dict with 'indexed' count.
    """
    documents = [
        {
            "content": f"[{seg['speaker_name']}, {_fmt_ts(seg['start'])}] {seg['text']}",
            "metadata": {
                "source": "transcriber",
                "recording_id": recording_id,
                "recording_filename": recording_filename,
                "speaker": seg["speaker_name"],
                "start_time": seg["start"],
                "end_time": seg["end"],
            },
        }
        for seg in segments
        if seg["text"].strip()
    ]
    indexer = _get_indexer()
    result = await indexer.add_documents(documents, collection_id=collection_id)
    logger.info(
        "KB push: recording=%s collection=%s docs=%s by=%s",
        recording_id, collection_id, len(documents), pushed_by,
    )
    return result
```

- [ ] **Step 4: Implement KB route**

```python
# autobot-backend/transcriber/routes/kb.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""KB push and status routes."""
from fastapi import APIRouter, Depends, HTTPException, Request
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import KbPushRequest, KbPushStatus
from transcriber.routes.export import _build_segment_list
from transcriber.knowledge.kb_push import push_to_kb

router = APIRouter(tags=["transcriber-kb"])


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else "default"


@router.post("/recordings/{recording_id}/kb/push")
async def kb_push(
    recording_id: int,
    body: KbPushRequest,
    request: Request,
    db: Database = Depends(get_db),
):
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    if rec["status"] != "complete":
        raise HTTPException(400, "Recording not yet transcribed")
    segments = await _build_segment_list(recording_id, db)
    result = await push_to_kb(
        recording_id=recording_id,
        recording_filename=rec["filename"],
        segments=segments,
        collection_id=body.collection_id,
        pushed_by=_user_id(request),
    )
    await db.create_kb_push(recording_id, body.collection_id, _user_id(request))
    return {"status": "ok", "indexed": result.get("indexed", len(segments))}


@router.get("/recordings/{recording_id}/kb/status", response_model=KbPushStatus)
async def kb_status(recording_id: int, db: Database = Depends(get_db)):
    push = await db.get_latest_kb_push(recording_id)
    if not push:
        return KbPushStatus(pushed=False, pushed_at=None, kb_collection_id=None, pushed_by=None)
    return KbPushStatus(
        pushed=True,
        pushed_at=push["pushed_at"],
        kb_collection_id=push["kb_collection_id"],
        pushed_by=push["pushed_by"],
    )
```

- [ ] **Step 5: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_kb_push.py -v
```
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/transcriber/knowledge/ \
        autobot-backend/transcriber/routes/kb.py \
        autobot-backend/transcriber/tests/test_kb_push.py
git commit -m "feat(transcriber): add manual KB push and status routes"
```

---

### Task 6: Wire all new routes into extension

**Files:**
- Modify: `autobot-backend/extensions/builtin/transcriber_extension.py`

- [ ] **Step 1: Update get_transcriber_router to include all routes**

Replace the `get_transcriber_router` function in [autobot-backend/extensions/builtin/transcriber_extension.py](autobot-backend/extensions/builtin/transcriber_extension.py):

```python
def get_transcriber_router() -> APIRouter:
    from transcriber.routes.projects import router as projects_router
    from transcriber.routes.recordings import router as recordings_router
    from transcriber.routes.transcripts import router as transcripts_router
    from transcriber.routes.export import router as export_router
    from transcriber.routes.ai import router as ai_router
    from transcriber.routes.kb import router as kb_router

    combined = APIRouter(prefix="/api/transcriber")
    combined.include_router(projects_router)
    combined.include_router(recordings_router)
    combined.include_router(transcripts_router)
    combined.include_router(export_router)
    combined.include_router(ai_router)
    combined.include_router(kb_router)
    return combined
```

- [ ] **Step 2: Run full backend test suite**

```bash
cd autobot-backend
python -m pytest transcriber/tests/ -v --tb=short
```
Expected: All PASSED, 0 failed

- [ ] **Step 3: Smoke-test all route imports**

```bash
cd autobot-backend
python -c "
from extensions.builtin.transcriber_extension import get_transcriber_router
r = get_transcriber_router()
routes = [str(r.path) for r in r.routes]
print(f'{len(routes)} routes registered')
print('OK')
"
```
Expected: prints route count and `OK`

- [ ] **Step 4: Commit**

```bash
git add autobot-backend/extensions/builtin/transcriber_extension.py
git commit -m "feat(transcriber): wire all feature routes into extension"
git tag transcriber-plan3-complete
```

---

**Plan 3 complete.** Full backend feature set: transcript editing, speaker renaming, notes, AI analysis, DOCX/PDF/SRT/VTT export, and manual KB push. Plan 4 builds the Vue 3 frontend.
