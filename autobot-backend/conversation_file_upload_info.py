# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The upload record ``ConversationFileManager`` passes between its helpers (#375).

Split out of ``conversation_file_manager.py`` (#20225) so that module stays under its size ceiling.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


@dataclass
class UploadInfo:
    """Issue #375: Dataclass to group file-related parameters and reduce function signatures.

    Groups commonly passed file attributes to reduce long parameter lists across
    _store_new_file, _insert_file_record, _build_file_response, and related methods.
    """

    file_id: str
    session_id: str
    original_filename: str
    stored_filename: str
    file_path: Path
    file_size: int
    file_hash: str
    mime_type: str | None = None
    uploaded_by: str | None = None
    message_id: str | None = None
    metadata: Dict[str, Any] | None = None
    deduplicated: bool = False

    def to_response_dict(self) -> Dict[str, Any]:
        """Convert to API response dictionary."""
        return {
            "file_id": self.file_id,
            "session_id": self.session_id,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "file_path": str(self.file_path),
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "mime_type": self.mime_type,
            "uploaded_by": self.uploaded_by,
            "uploaded_at": datetime.now(tz=timezone.utc).isoformat(),
            "deduplicated": self.deduplicated,
        }

    def to_db_tuple(self) -> tuple:
        """Convert to database insert tuple (for conversation_files table)."""
        return (
            self.file_id,
            self.session_id,
            self.original_filename,
            self.stored_filename,
            str(self.file_path),
            self.file_size,
            self.file_hash,
            self.mime_type,
            self.uploaded_by,
        )
