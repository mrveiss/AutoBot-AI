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

    # ── Speakers ──────────────────────────────────────────────────────────────

    async def create_speaker(
        self, recording_id: int, label: str, display_name: str, language: str | None
    ) -> int:
        cur = await self._conn.execute(
            "INSERT INTO speakers (recording_id, label, display_name, language) VALUES (?,?,?,?)",
            (recording_id, label, display_name, language),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def list_speakers(self, recording_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM speakers WHERE recording_id=? ORDER BY id", (recording_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_speaker(self, speaker_id: int, display_name: str) -> None:
        await self._conn.execute(
            "UPDATE speakers SET display_name=? WHERE id=?", (display_name, speaker_id)
        )
        await self._conn.commit()

    # ── Segments ──────────────────────────────────────────────────────────────

    async def create_segment(
        self,
        recording_id: int,
        speaker_id: int | None,
        start_time: float,
        end_time: float,
        text: str,
        is_overlap: bool = False,
    ) -> int:
        cur = await self._conn.execute(
            """INSERT INTO segments
               (recording_id, speaker_id, start_time, end_time, text, original_text, is_overlap)
               VALUES (?,?,?,?,?,?,?)""",
            (recording_id, speaker_id, start_time, end_time, text, text, int(is_overlap)),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def list_segments(self, recording_id: int) -> list[dict]:
        cur = await self._conn.execute(
            "SELECT * FROM segments WHERE recording_id=? ORDER BY start_time", (recording_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_segment_text(self, segment_id: int, text: str) -> None:
        await self._conn.execute(
            "UPDATE segments SET text=?, is_edited=1 WHERE id=?", (text, segment_id)
        )
        await self._conn.commit()

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
