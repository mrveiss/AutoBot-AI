# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Transcriber Database
# Issue #9044

"""Database operations for transcriber module."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiosqlite

from autobot_shared.logging_manager import get_logger
from transcriber.models import Recording, RecordingStatus, TranscriptionSegment

logger = get_logger(__name__)


class TranscriberDatabase:
    """Transcriber database operations (SQLite)."""

    def __init__(self, db_path: str = "data/transcriber.db"):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        # Ensure data directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transcriber_recording (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    duration REAL,
                    language TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
                """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transcriber_segment (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    recording_id INTEGER NOT NULL,
                    speaker_label TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    text TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (recording_id) REFERENCES transcriber_recording(id)
                )
                """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_segment_recording ON transcriber_segment(recording_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_recording_user ON transcriber_recording(user_id)")

            # Migration: Add user_id column if it doesn't exist
            cursor = await db.execute("PRAGMA table_info(transcriber_recording)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if "user_id" not in column_names:
                logger.warning("Migrating transcriber_recording table: adding user_id column")
                # For existing records, set a placeholder user_id
                # In production, these should be marked for manual review or deleted
                await db.execute("""
                    ALTER TABLE transcriber_recording ADD COLUMN user_id TEXT DEFAULT 'unknown-user'
                """)
                logger.warning("Migration complete: existing recordings assigned 'unknown-user' as user_id")

            await db.commit()
            logger.info("Transcriber database initialized at %s", self.db_path)

    async def create_recording(
        self, filename: str, file_path: str, user_id: str, metadata: Optional[dict] = None
    ) -> Recording:
        """Create a new recording entry.

        Args:
            filename: Original filename
            file_path: Path to audio file
            user_id: User ID who owns this recording
            metadata: Optional metadata dictionary

        Returns:
            Created Recording object
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO transcriber_recording (filename, file_path, user_id, status, metadata)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    filename,
                    file_path,
                    user_id,
                    RecordingStatus.PENDING.value,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            await db.commit()
            recording_id = cursor.lastrowid

            # Fetch the created recording
            cursor = await db.execute("SELECT * FROM transcriber_recording WHERE id = ?", (recording_id,))
            row = await cursor.fetchone()

            return self._row_to_recording(row)

    async def get_recording(self, recording_id: int, user_id: Optional[str] = None) -> Optional[Recording]:
        """Get recording by ID with optional ownership check.

        Args:
            recording_id: Recording ID
            user_id: Optional user ID for ownership verification (returns None if mismatch)

        Returns:
            Recording object or None if not found or ownership check fails
        """
        async with aiosqlite.connect(self.db_path) as db:
            if user_id is not None:
                # Include ownership check
                cursor = await db.execute(
                    "SELECT * FROM transcriber_recording WHERE id = ? AND user_id = ?", (recording_id, user_id)
                )
            else:
                # No ownership check (for internal use)
                cursor = await db.execute("SELECT * FROM transcriber_recording WHERE id = ?", (recording_id,))

            row = await cursor.fetchone()

            if row is None:
                return None

            return self._row_to_recording(row)

    async def update_recording_status(
        self,
        recording_id: int,
        status: RecordingStatus,
        duration: Optional[float] = None,
        language: Optional[str] = None,
    ) -> None:
        """Update recording status and optional fields.

        Args:
            recording_id: Recording ID
            status: New status
            duration: Optional audio duration in seconds
            language: Optional detected language code
        """
        async with aiosqlite.connect(self.db_path) as db:
            updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
            params = [status.value]

            if duration is not None:
                updates.append("duration = ?")
                params.append(duration)

            if language is not None:
                updates.append("language = ?")
                params.append(language)

            params.append(recording_id)

            await db.execute(
                f"""
                UPDATE transcriber_recording
                SET {', '.join(updates)}
                WHERE id = ?
                """,
                params,
            )
            await db.commit()

    async def create_segments(self, segments: List[dict], recording_id: int) -> List[TranscriptionSegment]:
        """Create transcription segments.

        Args:
            segments: List of segment dictionaries with speaker_label, start_time, end_time, text, confidence
            recording_id: Recording ID

        Returns:
            List of created TranscriptionSegment objects
        """
        async with aiosqlite.connect(self.db_path) as db:
            segment_ids = []

            for seg in segments:
                cursor = await db.execute(
                    """
                    INSERT INTO transcriber_segment
                    (recording_id, speaker_label, start_time, end_time, text, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        recording_id,
                        seg["speaker_label"],
                        seg["start_time"],
                        seg["end_time"],
                        seg["text"],
                        seg["confidence"],
                    ),
                )
                segment_ids.append(cursor.lastrowid)

            await db.commit()

            # Fetch created segments
            placeholders = ",".join("?" * len(segment_ids))
            cursor = await db.execute(
                f"SELECT * FROM transcriber_segment WHERE id IN ({placeholders})",
                segment_ids,
            )
            rows = await cursor.fetchall()

            return [self._row_to_segment(row) for row in rows]

    async def get_recording_segments(self, recording_id: int) -> List[TranscriptionSegment]:
        """Get all segments for a recording.

        Args:
            recording_id: Recording ID

        Returns:
            List of TranscriptionSegment objects ordered by start_time
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT * FROM transcriber_segment
                WHERE recording_id = ?
                ORDER BY start_time ASC
                """,
                (recording_id,),
            )
            rows = await cursor.fetchall()

            return [self._row_to_segment(row) for row in rows]

    def _row_to_recording(self, row) -> Recording:
        """Convert database row to Recording object."""
        metadata_json = row[9]
        metadata = json.loads(metadata_json) if metadata_json else None

        return Recording(
            id=row[0],
            filename=row[1],
            file_path=row[2],
            user_id=row[3],
            duration=row[4],
            language=row[5],
            status=RecordingStatus(row[6]),
            created_at=datetime.fromisoformat(row[7]),
            updated_at=datetime.fromisoformat(row[8]),
            metadata=metadata,
        )

    def _row_to_segment(self, row) -> TranscriptionSegment:
        """Convert database row to TranscriptionSegment object."""
        return TranscriptionSegment(
            id=row[0],
            recording_id=row[1],
            speaker_label=row[2],
            start_time=row[3],
            end_time=row[4],
            text=row[5],
            confidence=row[6],
            created_at=datetime.fromisoformat(row[7]),
        )


# Singleton instance
_transcriber_db: Optional[TranscriberDatabase] = None


async def get_transcriber_db() -> TranscriberDatabase:
    """Get or create transcriber database singleton.

    Returns:
        TranscriberDatabase instance
    """
    global _transcriber_db
    if _transcriber_db is None:
        _transcriber_db = TranscriberDatabase()
        await _transcriber_db.initialize()
    return _transcriber_db


# Backward compatibility alias
Database = TranscriberDatabase
