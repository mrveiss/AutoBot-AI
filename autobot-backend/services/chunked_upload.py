# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resumable uploads, staged on disk one chunk at a time (#19713).

A session is a directory holding the staged file and ``session.json``, so a restart loses nothing and
any worker can take the next chunk. The bytes on disk are the record of what arrived: a chunk counts
only once it is written whole and its checksum matched, and anything else is cut back off, so a
client resumes from the offset it is told. An unfinished session past its TTL stops taking chunks and
is listed for review; nothing here deletes one except the person cancelling it or a recorded handoff.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import AsyncIterable, Iterator, List, Optional

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_MB = 1024 * 1024
CHUNK_BYTES = env_int_clamped("AUTOBOT_UPLOAD_CHUNK_MB", 8, 1, 512) * _MB
MAX_TOTAL_BYTES = env_int_clamped("AUTOBOT_UPLOAD_MAX_TOTAL_MB", 8192, 1, 1048576) * _MB
SESSION_TTL_S = env_int_clamped("AUTOBOT_UPLOAD_SESSION_TTL_HOURS", 48, 1, 8760) * 3600
_READ_BYTES = _MB
_META = "session.json"
_LOCK = "session.lock"


class UploadSessionNotFound(Exception):
    """No such session, or it belongs to someone else; the two read the same."""


class UploadOffsetMismatch(Exception):
    """The chunk isn't the next one; ``received`` says where to resume."""

    def __init__(self, received: int) -> None:
        super().__init__(f"expected offset {received}")
        self.received = received


class UploadRejected(Exception):
    """The chunk or session breaks a rule; nothing was kept."""


class UploadBusy(Exception):
    """Another request is working on this session."""


@dataclass
class UploadSession:
    id: str
    owner: str
    filename: str
    total_size: int
    created_at: float
    received: int = 0
    state: str = "receiving"  # receiving | handing_off | failed | done
    sha256: str = ""
    result: dict = field(default_factory=dict)
    error: str = ""
    params: dict = field(default_factory=dict)
    handoff_started_at: float = 0.0

    @property
    def expired(self) -> bool:
        return self.state == "receiving" and time.time() - self.created_at > SESSION_TTL_S

    @property
    def handoff_lost(self) -> bool:
        """Its worker went away mid-handoff; the file is still here, so it can be tried again."""
        return self.state == "handing_off" and time.time() - self.handoff_started_at > SESSION_TTL_S


def staging_root() -> Path:
    configured = os.environ.get("AUTOBOT_UPLOAD_STAGING_DIR", "").strip()
    if configured:
        return Path(configured)
    from autobot_shared.ssot_config import get_config

    return Path(get_config().path.data_path) / "uploads-staging"


def _directory(upload_id: str) -> Path:
    """The id came from a URL, so only a real UUID's own text reaches a path."""
    try:
        canonical = str(uuid.UUID(upload_id))
    except ValueError as exc:
        raise UploadSessionNotFound(upload_id) from exc
    if canonical != upload_id:
        raise UploadSessionNotFound(upload_id)
    return staging_root() / canonical


def staged_path(session: UploadSession) -> Path:
    """Keeps the extension, because the transcriber's tools read the type from it."""
    return _directory(session.id) / f"data{Path(session.filename).suffix.lower()}"


def _save(session: UploadSession) -> None:
    directory = _directory(session.id)
    temp = directory / f"{_META}.tmp"
    temp.write_text(json.dumps(asdict(session)), encoding="utf-8")
    os.replace(temp, directory / _META)


def _load(upload_id: str) -> UploadSession:
    try:
        raw = (_directory(upload_id) / _META).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise UploadSessionNotFound(upload_id) from exc
    return UploadSession(**json.loads(raw))


def create_session(owner: str, filename: str, total_size: int, max_bytes: int, params: dict) -> UploadSession:
    """Start a session; the caller has already judged the filename for what it is being uploaded for."""
    if total_size <= 0 or total_size > min(max_bytes, MAX_TOTAL_BYTES):
        raise UploadRejected(f"size must be between 1 byte and {min(max_bytes, MAX_TOTAL_BYTES)} bytes")
    session = UploadSession(str(uuid.uuid4()), owner, filename, total_size, time.time(), params=params)
    directory = _directory(session.id)
    directory.mkdir(parents=True, mode=0o700)
    staged_path(session).touch(mode=0o600)
    _save(session)
    return session


def get_upload_session(upload_id: str, owner: str) -> UploadSession:
    session = _load(upload_id)
    if session.owner != owner:
        raise UploadSessionNotFound(upload_id)
    return session


class _Locked:
    """One request at a time on a session, across workers. Taking it doesn't wait, so it can't block the loop."""

    def __init__(self, upload_id: str) -> None:
        self._path = _directory(upload_id) / _LOCK

    def __enter__(self) -> "_Locked":
        self._fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(self._fd)
            raise UploadBusy("another request is working on this upload") from exc
        return self

    def __exit__(self, *_exc: object) -> None:
        os.close(self._fd)


def _check_chunk_allowed(session: UploadSession, offset: int) -> None:
    if session.state != "receiving" or session.expired:
        raise UploadRejected(f"this upload is {'expired' if session.expired else session.state}")
    if offset != session.received:
        raise UploadOffsetMismatch(session.received)


async def _stage(handle, chunks: AsyncIterable[bytes], limit: int) -> tuple[int, str]:
    written, digest = 0, hashlib.sha256()
    async for piece in chunks:
        written += len(piece)
        if written > limit:
            raise UploadRejected(f"a chunk here may hold at most {limit} bytes")
        digest.update(piece)
        await asyncio.to_thread(handle.write, piece)
    return written, digest.hexdigest()


def _cap(session: UploadSession, offset: int) -> int:
    return min(CHUNK_BYTES, session.total_size - offset)


def _open_at(path: Path, offset: int):
    handle = open(path, "r+b")
    handle.truncate(offset)
    handle.seek(offset)
    return handle


def _cut_back(handle, offset: int) -> None:
    handle.flush()
    handle.truncate(offset)


async def write_chunk(
    session: UploadSession, offset: int, chunks: AsyncIterable[bytes], expected_sha256: str = ""
) -> UploadSession:
    """Append the chunk at *offset*; on any failure the staged file is cut back and nothing is counted."""
    with _Locked(session.id):
        session = await asyncio.to_thread(_load, session.id)
        _check_chunk_allowed(session, offset)
        handle = await asyncio.to_thread(_open_at, staged_path(session), offset)
        try:
            written, digest = await _stage(handle, chunks, _cap(session, offset))
            if expected_sha256 and digest != expected_sha256.lower():
                raise UploadRejected("the chunk's checksum doesn't match, so it wasn't kept")
            if not written:
                raise UploadRejected("the chunk is empty")
            await asyncio.to_thread(handle.flush)
        except BaseException:  # a dropped connection too: only whole chunks count
            _cut_back(handle, offset)  # not awaited: a cancelled request must still cut back
            raise
        finally:
            handle.close()
        session.received = offset + written
        await asyncio.to_thread(_save, session)
        return session


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for piece in iter(lambda: handle.read(_READ_BYTES), b""):
            digest.update(piece)
    return digest.hexdigest()


async def begin_handoff(session: UploadSession) -> UploadSession:
    """All bytes arrived: fix the file's checksum and mark it, so two requests can't both hand it over."""
    with _Locked(session.id):
        session = await asyncio.to_thread(_load, session.id)
        if session.state not in ("receiving", "failed") and not session.handoff_lost:
            raise UploadRejected(f"this upload is {session.state}")
        if session.received != session.total_size:
            raise UploadOffsetMismatch(session.received)
        session.sha256 = await asyncio.to_thread(_sha256_of, staged_path(session))
        session.state, session.error, session.handoff_started_at = "handing_off", "", time.time()
        await asyncio.to_thread(_save, session)
        return session


def record_handoff(session: UploadSession, result: dict) -> None:
    """Recorded first, and only then is the staged file removed; the session stays as the record."""
    session.state, session.result = "done", result
    _save(session)
    staged_path(session).unlink(missing_ok=True)


def record_handoff_failure(session: UploadSession, error: str) -> None:
    """The file stays, so the person can try again without sending it again."""
    session.state, session.error = "failed", error
    _save(session)


def cancel_session(session: UploadSession) -> None:
    """The person's own decision; a handoff in progress is theirs to wait for."""
    with _Locked(session.id):
        current = _load(session.id)
        if current.state == "handing_off" and not current.handoff_lost:
            raise UploadRejected("this upload is being handed over")
    shutil.rmtree(_directory(session.id))


def _all_sessions() -> Iterator[UploadSession]:
    root = staging_root()
    if not root.is_dir():
        return
    for directory in root.iterdir():
        try:
            yield _load(directory.name)
        except (UploadSessionNotFound, ValueError, TypeError):
            logger.warning("Unreadable upload session in the staging directory: %s", directory.name)


def expired_sessions() -> List[UploadSession]:
    """Abandoned sessions, for a person to review: listed, never deleted here."""
    return [session for session in _all_sessions() if session.expired or session.handoff_lost]


def describe_upload(session: UploadSession, chunk_bytes: Optional[int] = None) -> dict:
    """What a client may see; the staging path and the owner stay on the server."""
    return {
        "upload_id": session.id,
        "filename": session.filename,
        "total_size": session.total_size,
        "received": session.received,
        "state": session.state,
        "expired": session.expired,
        "sha256": session.sha256,
        "result": session.result,
        "error": session.error,
        "chunk_bytes": chunk_bytes or CHUNK_BYTES,
    }
