# Transcriber Module — Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the transcriber module package with its SQLite sidecar database, Pydantic models, extension registration, and Projects/Recordings CRUD API — everything downstream plans depend on.

**Architecture:** Self-contained `autobot-backend/transcriber/` package registered as a builtin extension via `extensions/builtin/transcriber_extension.py`. Routes mounted through `feature_routers.py`. DB is a dedicated aiosqlite SQLite sidecar at `data/transcriber/transcriber.db`. Toggle via `VITE_FEATURE_TRANSCRIBER=true` (frontend) and `TRANSCRIBER_ENABLED=true` (backend).

**Tech Stack:** Python 3.11+, FastAPI, aiosqlite, Pydantic v2, autobot_shared (ssot_config, logging_manager, redis_client)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `autobot-backend/transcriber/__init__.py` | Package root |
| Create | `autobot-backend/transcriber/database.py` | aiosqlite CRUD + schema init |
| Create | `autobot-backend/transcriber/models.py` | Pydantic request/response schemas |
| Create | `autobot-backend/transcriber/deps.py` | `get_db()` FastAPI dependency |
| Create | `autobot-backend/transcriber/routes/__init__.py` | Routes package |
| Create | `autobot-backend/transcriber/routes/projects.py` | Project CRUD |
| Create | `autobot-backend/transcriber/routes/recordings.py` | Recording upload + list + delete |
| Create | `autobot-backend/extensions/builtin/transcriber_extension.py` | Extension wrapper + router |
| Modify | `autobot-backend/extensions/builtin/__init__.py` | Export TranscriberExtension |
| Modify | `autobot-backend/initialization/router_registry/feature_routers.py` | Register transcriber router |
| Modify | `autobot-frontend/src/config/navItems.ts` | Add transcriber nav entry |
| Modify | `autobot-frontend/src/router/index.ts` | Add /transcriber routes |
| Create | `autobot-backend/transcriber/tests/__init__.py` | Test package |
| Create | `autobot-backend/transcriber/tests/test_database.py` | DB CRUD tests |
| Create | `autobot-backend/transcriber/tests/test_projects_api.py` | Project route tests |
| Create | `autobot-backend/transcriber/tests/test_recordings_api.py` | Recording route tests |

---

### Task 1: Package scaffold + DB schema

**Files:**
- Create: `autobot-backend/transcriber/__init__.py`
- Create: `autobot-backend/transcriber/database.py`
- Create: `autobot-backend/transcriber/tests/__init__.py`
- Create: `autobot-backend/transcriber/tests/test_database.py`

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/transcriber/tests/test_database.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
import pytest_asyncio
from transcriber.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    await d.connect()
    yield d
    await d.close()


@pytest.mark.asyncio
async def test_create_and_get_project(db):
    pid = await db.create_project("My Project", "A test project", user_id="u1")
    assert isinstance(pid, int)
    project = await db.get_project(pid)
    assert project["name"] == "My Project"
    assert project["description"] == "A test project"
    assert project["user_id"] == "u1"


@pytest.mark.asyncio
async def test_list_projects_user_scoped(db):
    await db.create_project("P1", "", user_id="u1")
    await db.create_project("P2", "", user_id="u2")
    results = await db.list_projects(user_id="u1")
    assert len(results) == 1
    assert results[0]["name"] == "P1"


@pytest.mark.asyncio
async def test_delete_project_cascades(db):
    pid = await db.create_project("P", "", user_id="u1")
    rid = await db.create_recording(pid, "file.wav", "/tmp/file.wav", user_id="u1")
    await db.delete_project(pid)
    assert await db.get_project(pid) is None
    assert await db.get_recording(rid) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_database.py -v
```
Expected: `ModuleNotFoundError: No module named 'transcriber'`

- [ ] **Step 3: Create the package root**

```python
# autobot-backend/transcriber/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Transcriber module — general-purpose audio transcription for AutoBot."""
```

```python
# autobot-backend/transcriber/tests/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

- [ ] **Step 4: Implement Database class**

```python
# autobot-backend/transcriber/database.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Transcriber SQLite sidecar — all CRUD for projects, recordings, speakers, segments, notes, kb_pushes."""
import aiosqlite
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    duration REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    speaker_count INTEGER DEFAULT 0,
    process_seconds REAL,
    engine_used TEXT,
    language_detected TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT NOT NULL,
    failure_stage TEXT,
    failure_reason TEXT
);
CREATE TABLE IF NOT EXISTS speakers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    display_name TEXT NOT NULL,
    language TEXT
);
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    speaker_id INTEGER REFERENCES speakers(id),
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    original_text TEXT NOT NULL DEFAULT '',
    is_edited INTEGER NOT NULL DEFAULT 0,
    is_overlap INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS kb_pushes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    kb_collection_id TEXT NOT NULL,
    pushed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pushed_by TEXT NOT NULL
);
PRAGMA foreign_keys = ON;
"""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_SCHEMA)
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.commit()
        logger.info("Transcriber DB connected: %s", self._path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ── Projects ──────────────────────────────────────────────────────────────

    async def create_project(self, name: str, description: str, user_id: str) -> int:
        cur = await self._conn.execute(
            "INSERT INTO projects (name, description, user_id) VALUES (?,?,?)",
            (name, description, user_id),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_project(self, project_id: int) -> dict | None:
        cur = await self._conn.execute("SELECT * FROM projects WHERE id=?", (project_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_projects(self, user_id: str) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM projects WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_project(self, project_id: int, name: str, description: str) -> None:
        await self._conn.execute(
            "UPDATE projects SET name=?, description=? WHERE id=?",
            (name, description, project_id),
        )
        await self._conn.commit()

    async def delete_project(self, project_id: int) -> None:
        await self._conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        await self._conn.commit()

    # ── Recordings ────────────────────────────────────────────────────────────

    async def create_recording(
        self, project_id: int, filename: str, filepath: str, user_id: str
    ) -> int:
        cur = await self._conn.execute(
            "INSERT INTO recordings (project_id, filename, filepath, user_id) VALUES (?,?,?,?)",
            (project_id, filename, filepath, user_id),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_recording(self, recording_id: int) -> dict | None:
        cur = await self._conn.execute("SELECT * FROM recordings WHERE id=?", (recording_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_recordings(self, project_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM recordings WHERE project_id=? ORDER BY uploaded_at DESC",
            (project_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_recording_status(
        self,
        recording_id: int,
        status: str,
        *,
        engine_used: str | None = None,
        language_detected: str | None = None,
        speaker_count: int | None = None,
        process_seconds: float | None = None,
        failure_stage: str | None = None,
        failure_reason: str | None = None,
    ) -> None:
        await self._conn.execute(
            """UPDATE recordings SET status=?,
               engine_used=COALESCE(?,engine_used),
               language_detected=COALESCE(?,language_detected),
               speaker_count=COALESCE(?,speaker_count),
               process_seconds=COALESCE(?,process_seconds),
               failure_stage=COALESCE(?,failure_stage),
               failure_reason=COALESCE(?,failure_reason)
               WHERE id=?""",
            (
                status, engine_used, language_detected, speaker_count,
                process_seconds, failure_stage, failure_reason, recording_id,
            ),
        )
        await self._conn.commit()

    async def delete_recording(self, recording_id: int) -> None:
        await self._conn.execute("DELETE FROM recordings WHERE id=?", (recording_id,))
        await self._conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_database.py -v
```
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/transcriber/
git commit -m "feat(transcriber): add package scaffold and SQLite sidecar DB"
```

---

### Task 2: Pydantic models + deps

**Files:**
- Create: `autobot-backend/transcriber/models.py`
- Create: `autobot-backend/transcriber/deps.py`

- [ ] **Step 1: Create models**

```python
# autobot-backend/transcriber/models.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pydantic request/response schemas for the transcriber module."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)


class ProjectOut(BaseModel):
    id: int
    name: str
    description: str
    created_at: datetime
    user_id: str


class RecordingOut(BaseModel):
    id: int
    project_id: int
    filename: str
    duration: float | None
    status: Literal["pending", "processing", "complete", "error"]
    speaker_count: int
    process_seconds: float | None
    engine_used: str | None
    language_detected: str | None
    uploaded_at: datetime
    failure_stage: str | None
    failure_reason: str | None


class SpeakerOut(BaseModel):
    id: int
    recording_id: int
    label: str
    display_name: str
    language: str | None


class SpeakerUpdate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class SegmentOut(BaseModel):
    id: int
    recording_id: int
    speaker_id: int | None
    start_time: float
    end_time: float
    text: str
    original_text: str
    is_edited: bool
    is_overlap: bool


class SegmentUpdate(BaseModel):
    text: str = Field(min_length=0, max_length=5000)


class NoteCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class NoteUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class NoteOut(BaseModel):
    id: int
    segment_id: int
    recording_id: int
    content: str
    created_at: datetime


class TranscriptOut(BaseModel):
    recording: RecordingOut
    speakers: list[SpeakerOut]
    segments: list[SegmentOut]


class ExportRequest(BaseModel):
    format: Literal["docx", "pdf", "srt", "vtt"]
    include_timestamps: bool = True
    include_notes: bool = True
    include_speaker_names: bool = True


class AiAskRequest(BaseModel):
    action: Literal["summarize", "key_facts", "protocol", "custom"]
    custom_question: str | None = None


class KbPushRequest(BaseModel):
    collection_id: str = Field(min_length=1, max_length=200)


class KbPushStatus(BaseModel):
    pushed: bool
    pushed_at: datetime | None
    kb_collection_id: str | None
    pushed_by: str | None
```

- [ ] **Step 2: Create deps**

```python
# autobot-backend/transcriber/deps.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""FastAPI dependency: provides the transcriber Database instance."""
from fastapi import Request
from transcriber.database import Database


async def get_db(request: Request) -> Database:
    return request.app.state.transcriber_db
```

- [ ] **Step 3: Commit**

```bash
git add autobot-backend/transcriber/models.py autobot-backend/transcriber/deps.py
git commit -m "feat(transcriber): add Pydantic models and DB dependency"
```

---

### Task 3: Projects API routes

**Files:**
- Create: `autobot-backend/transcriber/routes/__init__.py`
- Create: `autobot-backend/transcriber/routes/projects.py`
- Create: `autobot-backend/transcriber/tests/test_projects_api.py`

- [ ] **Step 1: Write failing tests**

```python
# autobot-backend/transcriber/tests/test_projects_api.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from transcriber.routes.projects import router
from transcriber.database import Database
from transcriber.deps import get_db


@pytest.fixture
def app(tmp_path):
    a = FastAPI()
    db = Database(str(tmp_path / "test.db"))

    async def override_db():
        return db

    a.dependency_overrides[get_db] = override_db
    a.include_router(router, prefix="/api/transcriber")

    @a.on_event("startup")
    async def startup():
        await db.connect()

    return a


@pytest.mark.asyncio
async def test_create_project(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await app.router.startup()
        r = await c.post("/api/transcriber/projects", json={"name": "My Project", "description": "desc"})
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "My Project"
        assert "id" in data


@pytest.mark.asyncio
async def test_list_projects(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await app.router.startup()
        await c.post("/api/transcriber/projects", json={"name": "P1", "description": ""})
        r = await c.get("/api/transcriber/projects")
        assert r.status_code == 200
        assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_delete_project(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await app.router.startup()
        r = await c.post("/api/transcriber/projects", json={"name": "P", "description": ""})
        pid = r.json()["id"]
        r2 = await c.delete(f"/api/transcriber/projects/{pid}")
        assert r2.status_code == 204
        r3 = await c.get(f"/api/transcriber/projects/{pid}")
        assert r3.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_projects_api.py -v
```
Expected: `ModuleNotFoundError: No module named 'transcriber.routes'`

- [ ] **Step 3: Implement routes**

```python
# autobot-backend/transcriber/routes/__init__.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
```

```python
# autobot-backend/transcriber/routes/projects.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Project CRUD routes for the transcriber module."""
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(tags=["transcriber-projects"])

_DEFAULT_USER = "default"  # replaced by real auth in Plan 2


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else _DEFAULT_USER


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, request: Request, db: Database = Depends(get_db)):
    pid = await db.create_project(body.name, body.description, user_id=_user_id(request))
    project = await db.get_project(pid)
    return ProjectOut(**project)


@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(request: Request, db: Database = Depends(get_db)):
    rows = await db.list_projects(user_id=_user_id(request))
    return [ProjectOut(**r) for r in rows]


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: Database = Depends(get_db)):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return ProjectOut(**project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(project_id: int, body: ProjectUpdate, db: Database = Depends(get_db)):
    if not await db.get_project(project_id):
        raise HTTPException(404, "Project not found")
    await db.update_project(project_id, body.name, body.description)
    return ProjectOut(**await db.get_project(project_id))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: int, db: Database = Depends(get_db)):
    if not await db.get_project(project_id):
        raise HTTPException(404, "Project not found")
    await db.delete_project(project_id)
    return Response(status_code=204)
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_projects_api.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/transcriber/routes/
git commit -m "feat(transcriber): add project CRUD routes"
```

---

### Task 4: Recordings API routes

**Files:**
- Create: `autobot-backend/transcriber/routes/recordings.py`
- Modify: `autobot-backend/transcriber/database.py` (add remaining Recording CRUD already written in Task 1)
- Create: `autobot-backend/transcriber/tests/test_recordings_api.py`

- [ ] **Step 1: Write failing tests**

```python
# autobot-backend/transcriber/tests/test_recordings_api.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import io
import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from transcriber.routes.projects import router as projects_router
from transcriber.routes.recordings import router as recordings_router
from transcriber.database import Database
from transcriber.deps import get_db


@pytest.fixture
def app(tmp_path):
    a = FastAPI()
    db = Database(str(tmp_path / "test.db"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    async def override_db():
        return db

    a.dependency_overrides[get_db] = override_db
    a.state.transcriber_upload_dir = str(upload_dir)
    a.include_router(projects_router, prefix="/api/transcriber")
    a.include_router(recordings_router, prefix="/api/transcriber")

    @a.on_event("startup")
    async def startup():
        await db.connect()

    return a


@pytest.mark.asyncio
async def test_upload_recording(app, tmp_path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await app.router.startup()
        r = await c.post("/api/transcriber/projects", json={"name": "P", "description": ""})
        pid = r.json()["id"]
        audio_bytes = b"RIFF" + b"\x00" * 100
        r2 = await c.post(
            f"/api/transcriber/projects/{pid}/recordings",
            files={"file": ("test.wav", io.BytesIO(audio_bytes), "audio/wav")},
        )
        assert r2.status_code == 202
        data = r2.json()
        assert data["status"] == "pending"
        assert data["project_id"] == pid


@pytest.mark.asyncio
async def test_list_recordings(app, tmp_path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await app.router.startup()
        r = await c.post("/api/transcriber/projects", json={"name": "P", "description": ""})
        pid = r.json()["id"]
        await c.post(
            f"/api/transcriber/projects/{pid}/recordings",
            files={"file": ("a.wav", io.BytesIO(b"RIFF" + b"\x00" * 10), "audio/wav")},
        )
        r2 = await c.get(f"/api/transcriber/projects/{pid}/recordings")
        assert r2.status_code == 200
        assert len(r2.json()) == 1


@pytest.mark.asyncio
async def test_delete_recording(app, tmp_path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await app.router.startup()
        r = await c.post("/api/transcriber/projects", json={"name": "P", "description": ""})
        pid = r.json()["id"]
        r2 = await c.post(
            f"/api/transcriber/projects/{pid}/recordings",
            files={"file": ("b.wav", io.BytesIO(b"RIFF" + b"\x00" * 10), "audio/wav")},
        )
        rid = r2.json()["id"]
        r3 = await c.delete(f"/api/transcriber/recordings/{rid}")
        assert r3.status_code == 204
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_recordings_api.py -v
```
Expected: `ModuleNotFoundError: No module named 'transcriber.routes.recordings'`

- [ ] **Step 3: Implement recordings routes**

```python
# autobot-backend/transcriber/routes/recordings.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Recording upload, list, delete routes. Pipeline trigger wired in Plan 2."""
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
import aiofiles
from transcriber.database import Database
from transcriber.deps import get_db
from transcriber.models import RecordingOut

router = APIRouter(tags=["transcriber-recordings"])

_ALLOWED_EXTENSIONS = {".wav", ".mp3", ".mp4", ".m4a", ".ogg", ".flac", ".webm"}


def _upload_dir(request: Request) -> Path:
    return Path(request.app.state.transcriber_upload_dir)


def _user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user.id if user else "default"


@router.post("/projects/{project_id}/recordings", response_model=RecordingOut, status_code=202)
async def upload_recording(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Database = Depends(get_db),
):
    if not await db.get_project(project_id):
        raise HTTPException(404, "Project not found")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported audio format: {ext}")
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest = _upload_dir(request) / safe_name
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)
    rid = await db.create_recording(
        project_id, file.filename or safe_name, str(dest), user_id=_user_id(request)
    )
    rec = await db.get_recording(rid)
    return RecordingOut(**rec)


@router.get("/projects/{project_id}/recordings", response_model=list[RecordingOut])
async def list_recordings(project_id: int, db: Database = Depends(get_db)):
    if not await db.get_project(project_id):
        raise HTTPException(404, "Project not found")
    rows = await db.list_recordings(project_id)
    return [RecordingOut(**r) for r in rows]


@router.get("/recordings/{recording_id}", response_model=RecordingOut)
async def get_recording(recording_id: int, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    return RecordingOut(**rec)


@router.delete("/recordings/{recording_id}", status_code=204)
async def delete_recording(recording_id: int, db: Database = Depends(get_db)):
    rec = await db.get_recording(recording_id)
    if not rec:
        raise HTTPException(404, "Recording not found")
    filepath = Path(rec["filepath"])
    if filepath.exists():
        filepath.unlink(missing_ok=True)
    await db.delete_recording(recording_id)
    return Response(status_code=204)
```

- [ ] **Step 4: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_recordings_api.py -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/transcriber/routes/recordings.py autobot-backend/transcriber/tests/test_recordings_api.py
git commit -m "feat(transcriber): add recording upload/list/delete routes"
```

---

### Task 5: Extension wrapper + feature router registration

**Files:**
- Create: `autobot-backend/extensions/builtin/transcriber_extension.py`
- Modify: `autobot-backend/extensions/builtin/__init__.py`
- Modify: `autobot-backend/initialization/router_registry/feature_routers.py`
- Create: `autobot-backend/transcriber/tests/test_extension.py`

- [ ] **Step 1: Write failing test**

```python
# autobot-backend/transcriber/tests/test_extension.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
from extensions.builtin.transcriber_extension import TranscriberExtension, get_transcriber_router


def test_transcriber_extension_name():
    ext = TranscriberExtension()
    assert ext.name == "transcriber"


def test_get_transcriber_router_returns_router():
    from fastapi import APIRouter
    router = get_transcriber_router()
    assert isinstance(router, APIRouter)
```

- [ ] **Step 2: Run to verify failure**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_extension.py -v
```
Expected: `ImportError: cannot import name 'TranscriberExtension'`

- [ ] **Step 3: Implement the extension**

```python
# autobot-backend/extensions/builtin/transcriber_extension.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Transcriber builtin extension.

Mounts all transcriber routes under /api/transcriber and manages
DB lifecycle (connect on app startup, close on shutdown).
Enabled via TRANSCRIBER_ENABLED=true in environment.
"""
import os
from pathlib import Path
from fastapi import APIRouter, FastAPI
from extensions.base import Extension, HookContext
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_ENABLED = os.getenv("TRANSCRIBER_ENABLED", "true").lower() == "true"
_DATA_DIR = Path(os.getenv("TRANSCRIBER_DATA_DIR", "data/transcriber"))


def get_transcriber_router() -> APIRouter:
    from transcriber.routes.projects import router as projects_router
    from transcriber.routes.recordings import router as recordings_router
    combined = APIRouter(prefix="/api/transcriber")
    combined.include_router(projects_router)
    combined.include_router(recordings_router)
    return combined


class TranscriberExtension(Extension):
    name = "transcriber"
    priority = 10

    async def on_app_startup(self, app: FastAPI) -> None:
        if not _ENABLED:
            logger.info("Transcriber extension disabled (TRANSCRIBER_ENABLED != true)")
            return
        from transcriber.database import Database
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR := _DATA_DIR / "uploads").mkdir(exist_ok=True)
        (_DATA_DIR / "processed").mkdir(exist_ok=True)
        (_DATA_DIR / "exports").mkdir(exist_ok=True)
        db = Database(str(_DATA_DIR / "transcriber.db"))
        await db.connect()
        app.state.transcriber_db = db
        app.state.transcriber_upload_dir = str(_DATA_DIR / "uploads")
        app.state.transcriber_export_dir = str(_DATA_DIR / "exports")
        logger.info("Transcriber extension started")

    async def on_app_shutdown(self, app: FastAPI) -> None:
        db = getattr(app.state, "transcriber_db", None)
        if db:
            await db.close()
            logger.info("Transcriber DB closed")
```

- [ ] **Step 4: Add to extensions/builtin/__init__.py**

Open [autobot-backend/extensions/builtin/__init__.py](autobot-backend/extensions/builtin/__init__.py) and add:

```python
from extensions.builtin.transcriber_extension import TranscriberExtension

__all__ = [
    "LoggingExtension",
    "PermissionEnforcementExtension",
    "SecretMaskingExtension",
    "TranscriberExtension",  # add this line
]
```

- [ ] **Step 5: Register in feature_routers.py**

In [autobot-backend/initialization/router_registry/feature_routers.py](autobot-backend/initialization/router_registry/feature_routers.py), find the `FEATURE_ROUTERS` config list and add:

```python
{
    "name": "transcriber",
    "module": "extensions.builtin.transcriber_extension",
    "router_fn": "get_transcriber_router",
    "prefix": "",       # prefix already embedded in router
    "tags": ["transcriber"],
    "enabled_env": "TRANSCRIBER_ENABLED",
    "enabled_default": "true",
},
```

(Follow the exact dict shape used by the existing entries in that file.)

- [ ] **Step 6: Run tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/test_extension.py -v
```
Expected: 2 PASSED

- [ ] **Step 7: Smoke-test import**

```bash
cd autobot-backend
python -c "from extensions.builtin.transcriber_extension import TranscriberExtension, get_transcriber_router; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add autobot-backend/extensions/builtin/transcriber_extension.py \
        autobot-backend/extensions/builtin/__init__.py \
        autobot-backend/initialization/router_registry/feature_routers.py \
        autobot-backend/transcriber/tests/test_extension.py
git commit -m "feat(transcriber): register extension and mount routes via feature_routers"
```

---

### Task 6: Frontend nav + route scaffolding

**Files:**
- Modify: `autobot-frontend/src/config/navItems.ts`
- Modify: `autobot-frontend/src/router/index.ts`
- Create: `autobot-frontend/src/views/transcriber/TranscriberLayout.vue`
- Create: `autobot-frontend/src/views/transcriber/ProjectsView.vue`
- Create: `autobot-frontend/src/views/transcriber/ProjectDetailView.vue`
- Create: `autobot-frontend/src/views/transcriber/TranscriptView.vue`

- [ ] **Step 1: Add nav entry to navItems.ts**

In [autobot-frontend/src/config/navItems.ts](autobot-frontend/src/config/navItems.ts), add to the `navItems` array:

```typescript
{
  to: '/transcriber',
  labelKey: 'nav.transcriber',
  icon: 'M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z',
  iconStroke: true,
  featureFlag: 'transcriber',
},
```

- [ ] **Step 2: Add routes to router/index.ts**

In [autobot-frontend/src/router/index.ts](autobot-frontend/src/router/index.ts), add to the `routes` array (after the existing route entries):

```typescript
{
  path: '/transcriber',
  component: () => import('@/views/transcriber/TranscriberLayout.vue'),
  meta: { requiresAuth: true, title: 'Transcriber', hideInNav: false },
  children: [
    {
      path: '',
      name: 'transcriber-projects',
      component: () => import('@/views/transcriber/ProjectsView.vue'),
      meta: { title: 'Projects' },
    },
    {
      path: 'projects/:projectId',
      name: 'transcriber-project-detail',
      component: () => import('@/views/transcriber/ProjectDetailView.vue'),
      meta: { title: 'Project' },
    },
    {
      path: 'projects/:projectId/recordings/:recordingId',
      name: 'transcriber-transcript',
      component: () => import('@/views/transcriber/TranscriptView.vue'),
      meta: { title: 'Transcript' },
    },
  ],
},
```

- [ ] **Step 3: Create placeholder layout**

```vue
<!-- autobot-frontend/src/views/transcriber/TranscriberLayout.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
// Layout shell — sidebar + content area. Components added in Plan 4.
</script>

<template>
  <div class="transcriber-layout">
    <RouterView />
  </div>
</template>
```

```vue
<!-- autobot-frontend/src/views/transcriber/ProjectsView.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
// Implemented in Plan 4.
</script>
<template><div>Projects — coming in Plan 4</div></template>
```

```vue
<!-- autobot-frontend/src/views/transcriber/ProjectDetailView.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
// Implemented in Plan 4.
</script>
<template><div>Project Detail — coming in Plan 4</div></template>
```

```vue
<!-- autobot-frontend/src/views/transcriber/TranscriptView.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
// Implemented in Plan 4.
</script>
<template><div>Transcript — coming in Plan 4</div></template>
```

- [ ] **Step 4: Type-check frontend**

```bash
cd autobot-frontend
npm run type-check
```
Expected: 0 errors

- [ ] **Step 5: Verify nav-items coverage test**

```bash
cd autobot-frontend
npm run test -- --run src/__tests__/nav-items-coverage.test.ts
```
Expected: PASS (transcriber route is `hideInNav: false` and present in navItems)

- [ ] **Step 6: Commit**

```bash
git add autobot-frontend/src/config/navItems.ts \
        autobot-frontend/src/router/index.ts \
        autobot-frontend/src/views/transcriber/
git commit -m "feat(transcriber): add frontend nav entry and route scaffolding"
```

---

### Task 7: Run full Plan 1 test suite

- [ ] **Step 1: Run all transcriber backend tests**

```bash
cd autobot-backend
python -m pytest transcriber/tests/ -v --tb=short
```
Expected: 11 PASSED, 0 failed

- [ ] **Step 2: Smoke-test import chain**

```bash
cd autobot-backend
python -c "
from transcriber.database import Database
from transcriber.models import ProjectCreate, RecordingOut
from transcriber.deps import get_db
from transcriber.routes.projects import router
from transcriber.routes.recordings import router as r2
from extensions.builtin.transcriber_extension import TranscriberExtension, get_transcriber_router
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Step 3: Final commit tag**

```bash
git tag transcriber-plan1-complete
```

---

**Plan 1 complete.** The transcriber package is wired into AutoBot: DB schema live, Projects + Recordings CRUD working, extension registered, frontend routes scaffolded. Plan 2 adds the processing pipeline.
