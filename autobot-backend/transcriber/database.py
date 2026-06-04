# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Transcriber SQLite sidecar — all CRUD for projects, recordings, speakers, segments, notes, kb_pushes."""

import os

import aiosqlite
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Each tuple is (version, sql). Append new entries; never reorder or delete.
# Migration 1 uses CREATE TABLE IF NOT EXISTS so it is safe to run against an
# existing pre-migration database — tables already present are left untouched
# and the version row is inserted, bringing the DB under version-tracked control.
_MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
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
""",
    ),
    (
        2,
        """
CREATE INDEX IF NOT EXISTS idx_recordings_project_id ON recordings(project_id);
CREATE INDEX IF NOT EXISTS idx_speakers_recording_id ON speakers(recording_id);
CREATE INDEX IF NOT EXISTS idx_segments_recording_id ON segments(recording_id);
CREATE INDEX IF NOT EXISTS idx_segments_speaker_id ON segments(speaker_id);
CREATE INDEX IF NOT EXISTS idx_notes_recording_id ON notes(recording_id);
CREATE INDEX IF NOT EXISTS idx_notes_segment_id ON notes(segment_id);
""",
    ),
]


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() has not been called")
        return self._conn

    async def connect(self) -> None:
        if self._conn is not None:
            return  # already connected — idempotent
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._run_migrations()
        logger.info("Transcriber DB connected: %s", self._path)

    async def _run_migrations(self) -> None:
        await self._db().execute(
            "CREATE TABLE IF NOT EXISTS _schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        await self._db().commit()
        cur = await self._db().execute("SELECT COALESCE(MAX(version), 0) FROM _schema_migrations")
        row = await cur.fetchone()
        current: int = row[0]
        for version, sql in _MIGRATIONS:
            if version <= current:
                continue
            await self._db().executescript(sql)
            await self._db().execute("INSERT INTO _schema_migrations (version) VALUES (?)", (version,))
            await self._db().commit()
            logger.info("Transcriber DB: applied migration %d", version)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ── Projects ──────────────────────────────────────────────────────────────

    async def create_project(self, name: str, description: str, user_id: str) -> int:
        cur = await self._db().execute(
            "INSERT INTO projects (name, description, user_id) VALUES (?,?,?)",
            (name, description, user_id),
        )
        await self._db().commit()
        return cur.lastrowid

    async def get_project(self, project_id: int) -> dict | None:
        cur = await self._db().execute("SELECT * FROM projects WHERE id=?", (project_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_projects(self, user_id: str, *, limit: int = 200, offset: int = 0) -> list[dict]:
        cur = await self._db().execute(
            "SELECT * FROM projects WHERE user_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_project(self, project_id: int, name: str, description: str) -> None:
        cur = await self._db().execute(
            "UPDATE projects SET name=?, description=? WHERE id=?",
            (name, description, project_id),
        )
        await self._db().commit()
        if cur.rowcount == 0:
            raise KeyError(f"no project with id={project_id}")

    async def delete_project(self, project_id: int) -> None:
        cur = await self._db().execute("DELETE FROM projects WHERE id=?", (project_id,))
        await self._db().commit()
        if cur.rowcount == 0:
            raise KeyError(f"no project with id={project_id}")

    # ── Recordings ────────────────────────────────────────────────────────────

    async def create_recording(self, project_id: int, filename: str, filepath: str, user_id: str) -> int:
        if not os.path.isabs(filepath):
            raise ValueError(f"filepath must be absolute, got: {filepath!r}")
        cur = await self._db().execute(
            "INSERT INTO recordings (project_id, filename, filepath, user_id) VALUES (?,?,?,?)",
            (project_id, filename, filepath, user_id),
        )
        await self._db().commit()
        return cur.lastrowid

    async def get_recording(self, recording_id: int) -> dict | None:
        cur = await self._db().execute("SELECT * FROM recordings WHERE id=?", (recording_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_recordings(self, project_id: int, *, limit: int = 200, offset: int = 0) -> list[dict]:
        cur = await self._db().execute(
            "SELECT * FROM recordings WHERE project_id=? ORDER BY uploaded_at DESC LIMIT ? OFFSET ?",
            (project_id, limit, offset),
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
        cur = await self._db().execute(
            """UPDATE recordings SET status=?,
               engine_used=COALESCE(?,engine_used),
               language_detected=COALESCE(?,language_detected),
               speaker_count=COALESCE(?,speaker_count),
               process_seconds=COALESCE(?,process_seconds),
               failure_stage=COALESCE(?,failure_stage),
               failure_reason=COALESCE(?,failure_reason)
               WHERE id=?""",
            (
                status,
                engine_used,
                language_detected,
                speaker_count,
                process_seconds,
                failure_stage,
                failure_reason,
                recording_id,
            ),
        )
        await self._db().commit()
        if cur.rowcount == 0:
            raise KeyError(f"no recording with id={recording_id}")

    async def delete_recording(self, recording_id: int) -> None:
        cur = await self._db().execute("DELETE FROM recordings WHERE id=?", (recording_id,))
        await self._db().commit()
        if cur.rowcount == 0:
            raise KeyError(f"no recording with id={recording_id}")

    # ── Speakers ──────────────────────────────────────────────────────────────

    async def create_speaker(self, recording_id: int, label: str, display_name: str, language: str | None) -> int:
        cur = await self._db().execute(
            "INSERT INTO speakers (recording_id, label, display_name, language) VALUES (?,?,?,?)",
            (recording_id, label, display_name, language),
        )
        await self._db().commit()
        return cur.lastrowid

    async def list_speakers(self, recording_id: int, *, limit: int = 200, offset: int = 0) -> list[dict]:
        cur = await self._db().execute(
            "SELECT * FROM speakers WHERE recording_id=? ORDER BY id LIMIT ? OFFSET ?",
            (recording_id, limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_speaker(self, speaker_id: int) -> dict | None:
        cur = await self._db().execute("SELECT * FROM speakers WHERE id=?", (speaker_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_speaker(self, speaker_id: int, display_name: str) -> None:
        cur = await self._db().execute("UPDATE speakers SET display_name=? WHERE id=?", (display_name, speaker_id))
        await self._db().commit()
        if cur.rowcount == 0:
            raise KeyError(f"no speaker with id={speaker_id}")

    async def merge_speakers(self, source_speaker_id: int, target_speaker_id: int) -> None:
        """Merge source speaker into target speaker. All segments referencing source will point to target, then source is deleted."""
        # Verify both speakers exist and belong to the same recording
        src_cur = await self._db().execute("SELECT recording_id FROM speakers WHERE id=?", (source_speaker_id,))
        src_row = await src_cur.fetchone()
        if not src_row:
            raise KeyError(f"no speaker with id={source_speaker_id}")

        tgt_cur = await self._db().execute("SELECT recording_id FROM speakers WHERE id=?", (target_speaker_id,))
        tgt_row = await tgt_cur.fetchone()
        if not tgt_row:
            raise KeyError(f"no speaker with id={target_speaker_id}")

        if src_row[0] != tgt_row[0]:
            raise ValueError("Cannot merge speakers from different recordings")

        if source_speaker_id == target_speaker_id:
            raise ValueError("Cannot merge a speaker into itself")

        # Update all segments that reference source speaker to point to target speaker
        await self._db().execute(
            "UPDATE segments SET speaker_id=? WHERE speaker_id=?", (target_speaker_id, source_speaker_id)
        )

        # Delete the source speaker
        await self._db().execute("DELETE FROM speakers WHERE id=?", (source_speaker_id,))
        await self._db().commit()

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
        cur = await self._db().execute(
            """INSERT INTO segments
               (recording_id, speaker_id, start_time, end_time, text, original_text, is_overlap)
               VALUES (?,?,?,?,?,?,?)""",
            (recording_id, speaker_id, start_time, end_time, text, text, int(is_overlap)),
        )
        await self._db().commit()
        return cur.lastrowid

    async def list_segments(self, recording_id: int, *, limit: int = 200, offset: int = 0) -> list[dict]:
        cur = await self._db().execute(
            "SELECT * FROM segments WHERE recording_id=? ORDER BY start_time LIMIT ? OFFSET ?",
            (recording_id, limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_segment(self, segment_id: int) -> dict | None:
        cur = await self._db().execute("SELECT * FROM segments WHERE id=?", (segment_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_segment_text(self, segment_id: int, text: str) -> None:
        cur = await self._db().execute("UPDATE segments SET text=?, is_edited=1 WHERE id=?", (text, segment_id))
        await self._db().commit()
        if cur.rowcount == 0:
            raise KeyError(f"no segment with id={segment_id}")

    # ── Notes ─────────────────────────────────────────────────────────────────

    async def create_note(self, segment_id: int, recording_id: int, content: str) -> int:
        cur = await self._db().execute(
            "INSERT INTO notes (segment_id, recording_id, content) VALUES (?,?,?)",
            (segment_id, recording_id, content),
        )
        await self._db().commit()
        return cur.lastrowid

    async def get_note(self, note_id: int) -> dict | None:
        cur = await self._db().execute("SELECT * FROM notes WHERE id=?", (note_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def list_notes(self, recording_id: int, *, limit: int = 200, offset: int = 0) -> list[dict]:
        cur = await self._db().execute(
            "SELECT * FROM notes WHERE recording_id=? ORDER BY created_at LIMIT ? OFFSET ?",
            (recording_id, limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def update_note(self, note_id: int, content: str) -> None:
        cur = await self._db().execute("UPDATE notes SET content=? WHERE id=?", (content, note_id))
        await self._db().commit()
        if cur.rowcount == 0:
            raise KeyError(f"no note with id={note_id}")

    async def delete_note(self, note_id: int) -> None:
        cur = await self._db().execute("DELETE FROM notes WHERE id=?", (note_id,))
        await self._db().commit()
        if cur.rowcount == 0:
            raise KeyError(f"no note with id={note_id}")

    # ── KB Pushes ─────────────────────────────────────────────────────────────

    async def create_kb_push(self, recording_id: int, kb_collection_id: str, pushed_by: str) -> int:
        cur = await self._db().execute(
            "INSERT INTO kb_pushes (recording_id, kb_collection_id, pushed_by) VALUES (?,?,?)",
            (recording_id, kb_collection_id, pushed_by),
        )
        await self._db().commit()
        return cur.lastrowid

    async def get_latest_kb_push(self, recording_id: int) -> dict | None:
        cur = await self._db().execute(
            "SELECT * FROM kb_pushes WHERE recording_id=? ORDER BY pushed_at DESC LIMIT 1",
            (recording_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


# ── Singleton ─────────────────────────────────────────────────────────────

_db_instance: Database | None = None


async def get_transcriber_db() -> Database:
    """Get or create the singleton transcriber database instance.

    Returns:
        Database: The shared database connection instance
    """
    global _db_instance
    if _db_instance is None:
        # Get database path from environment, default to data/transcriber.db
        db_path = os.getenv("AUTOBOT_TRANSCRIBER_DB_PATH", "data/transcriber.db")
        _db_instance = Database(db_path)
        await _db_instance.connect()
        await _db_instance.migrate()
        logger.info(f"Transcriber database initialized at {db_path}")
    return _db_instance
