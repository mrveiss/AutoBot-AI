# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Snapshot index for resumable agent sessions (GH#4458).

Maintains a JSON file-based index of container snapshot metadata.
Snapshots are Docker images created via ``docker commit``.
"""

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from pathlib import Path
from typing import Dict, List, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_DEFAULT_SNAPSHOT_PATH = "/opt/autobot/snapshots"
_INDEX_FILENAME = "snapshot_index.json"

_SNAPSHOT_STORAGE_PATH: str = os.getenv("AUTOBOT_SNAPSHOT_STORAGE_PATH", _DEFAULT_SNAPSHOT_PATH)


def _resolve_storage_path() -> Path:
    raw = os.getenv("AUTOBOT_SNAPSHOT_STORAGE_PATH", _DEFAULT_SNAPSHOT_PATH)
    if not raw:
        logger.warning(
            "AUTOBOT_SNAPSHOT_STORAGE_PATH is empty, using default %s",
            _DEFAULT_SNAPSHOT_PATH,
        )
        raw = _DEFAULT_SNAPSHOT_PATH
    path = Path(raw)
    if str(path).startswith("/tmp"):
        logger.warning(
            "Snapshot storage path %s is under /tmp — snapshots will not survive a host restart. "
            "Set AUTOBOT_SNAPSHOT_STORAGE_PATH to a persistent directory (e.g. /opt/autobot/snapshots).",
            path,
        )
    return path


@dataclass
class SnapshotRecord:
    """Metadata for one container snapshot."""

    snapshot_id: str
    session_id: str
    container_id: str
    image_name: str
    created_at: str
    size_bytes: int = 0
    labels: Dict[str, str] = field(default_factory=dict)
    user_id: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "SnapshotRecord":
        # Filter to known fields so future schema additions don't crash older code.
        known = {f.name for f in dataclass_fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


class SnapshotIndex:
    """File-backed index of container snapshot records (GH#4458).

    Thread-safety: all operations are protected by a threading lock (GH#8968).
    Each operation re-reads and re-writes the index file under lock protection,
    ensuring consistency under concurrent access in multi-worker deployments.
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self._storage_path = storage_path or _resolve_storage_path()
        self._index_path = self._storage_path / _INDEX_FILENAME
        self._lock = threading.Lock()

    def _ensure_storage(self) -> None:
        self._storage_path.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, dict]:
        if not self._index_path.exists():
            return {}
        try:
            with open(self._index_path, encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load snapshot index, starting fresh: %s", exc)
            return {}

    def _save(self, records: Dict[str, dict]) -> None:
        self._ensure_storage()
        tmp = self._index_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
        tmp.replace(self._index_path)

    def add(self, record: SnapshotRecord) -> None:
        with self._lock:
            records = self._load()
            records[record.snapshot_id] = record.to_dict()
            self._save(records)
            logger.debug("Snapshot %s added to index", record.snapshot_id)

    def get(self, snapshot_id: str) -> Optional[SnapshotRecord]:
        with self._lock:
            records = self._load()
            data = records.get(snapshot_id)
            if data is None:
                return None
            try:
                return SnapshotRecord.from_dict(data)
            except (TypeError, KeyError) as exc:
                logger.warning("Malformed snapshot record for %s: %s", snapshot_id, exc)
                return None

    def list_by_session(self, session_id: str) -> List[SnapshotRecord]:
        with self._lock:
            records = self._load()
            result = []
            for v in records.values():
                if v.get("session_id") != session_id:
                    continue
                try:
                    result.append(SnapshotRecord.from_dict(v))
                except (TypeError, KeyError) as exc:
                    logger.warning("Skipping malformed snapshot record: %s", exc)
            return result

    def list_all(self) -> List[SnapshotRecord]:
        with self._lock:
            records = self._load()
            result = []
            for v in records.values():
                try:
                    result.append(SnapshotRecord.from_dict(v))
                except (TypeError, KeyError) as exc:
                    logger.warning("Skipping malformed snapshot record: %s", exc)
            return result

    def list_by_user(self, user_id: str) -> List[SnapshotRecord]:
        """List all snapshots owned by a specific user.

        Args:
            user_id: User identifier to filter by

        Returns:
            List of SnapshotRecord objects owned by the user
        """
        with self._lock:
            records = self._load()
            result = []
            for v in records.values():
                if v.get("user_id") != user_id:
                    continue
                try:
                    result.append(SnapshotRecord.from_dict(v))
                except (TypeError, KeyError) as exc:
                    logger.warning("Skipping malformed snapshot record: %s", exc)
            return result

    def remove(self, snapshot_id: str) -> bool:
        with self._lock:
            records = self._load()
            if snapshot_id not in records:
                return False
            del records[snapshot_id]
            self._save(records)
            logger.debug("Snapshot %s removed from index", snapshot_id)
            return True


def make_snapshot_id() -> str:
    return uuid.uuid4().hex[:16]


def _image_name_for_snapshot(snapshot_id: str) -> str:
    return f"autobot-snapshot-{snapshot_id}:latest"
