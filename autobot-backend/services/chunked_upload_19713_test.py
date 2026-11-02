# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#19713: chunks reach disk whole or not at all, and an interrupted upload resumes where it says."""

from __future__ import annotations

import asyncio
import errno
import hashlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services import chunked_upload as uploads

_DATA = bytes(range(256)) * 400  # 102,400 bytes


@pytest.fixture(autouse=True)
def _staging(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOBOT_UPLOAD_STAGING_DIR", str(tmp_path))
    monkeypatch.setattr(uploads, "CHUNK_BYTES", 40_000)


def _staged_bytes(session: uploads.UploadSession) -> bytes:
    return uploads.staged_path(session).read_bytes()


async def _body(*pieces: bytes):
    for piece in pieces:
        yield piece


def _session(size: int = len(_DATA), name: str = "talk.mp4") -> uploads.UploadSession:
    return uploads.create_session("alice", name, size, uploads.MAX_TOTAL_BYTES, {"target": "transcript"})


async def _send_all(session: uploads.UploadSession) -> uploads.UploadSession:
    offset = 0
    while offset < len(_DATA):
        piece = _DATA[offset : offset + uploads.CHUNK_BYTES]
        session = await uploads.write_chunk(session, offset, _body(piece), hashlib.sha256(piece).hexdigest())
        offset = session.received
    return session


@pytest.mark.asyncio
async def test_n_chunks_stage_the_whole_file_with_its_size_and_checksum() -> None:
    session = await uploads.begin_handoff(await _send_all(_session()))
    assert _staged_bytes(session) == _DATA and uploads.staged_path(session).suffix == ".mp4"
    await asyncio.to_thread(uploads.verify_checksum, session)
    assert session.sha256 == hashlib.sha256(_DATA).hexdigest()


@pytest.mark.asyncio
async def test_a_connection_dropped_mid_chunk_resumes_from_the_last_whole_one() -> None:
    session = _session()
    first = _DATA[:40_000]
    session = await uploads.write_chunk(session, 0, _body(first))

    async def dropped():
        yield _DATA[40_000:50_000]
        raise ConnectionError("gone")

    with pytest.raises(ConnectionError):
        await uploads.write_chunk(session, 40_000, dropped())
    resumed = uploads.get_upload_session(session.id, "alice")
    assert resumed.received == 40_000
    assert uploads.staged_path(resumed).stat().st_size == 40_000, "the partial chunk isn't left behind"
    offset = resumed.received
    while offset < len(_DATA):
        resumed = await uploads.write_chunk(resumed, offset, _body(_DATA[offset : offset + 40_000]))
        offset = resumed.received
    assert _staged_bytes(resumed) == _DATA


@pytest.mark.asyncio
async def test_a_chunk_at_the_wrong_offset_says_where_to_resume() -> None:
    session = await uploads.write_chunk(_session(), 0, _body(_DATA[:100]))
    with pytest.raises(uploads.UploadOffsetMismatch) as caught:
        await uploads.write_chunk(session, 0, _body(_DATA[:100]))
    assert caught.value.received == 100


@pytest.mark.asyncio
async def test_a_bad_checksum_keeps_nothing() -> None:
    session = _session()
    with pytest.raises(uploads.UploadRejected, match="checksum"):
        await uploads.write_chunk(session, 0, _body(_DATA[:100]), "0" * 64)
    assert uploads.get_upload_session(session.id, "alice").received == 0
    assert uploads.staged_path(session).stat().st_size == 0


@pytest.mark.asyncio
async def test_a_chunk_over_the_limit_is_refused_and_cut_back() -> None:
    session = _session()
    with pytest.raises(uploads.UploadRejected, match="at most"):
        await uploads.write_chunk(session, 0, _body(_DATA[:30_000], _DATA[30_000:60_000]))
    assert uploads.staged_path(session).stat().st_size == 0


@pytest.mark.asyncio
async def test_a_chunk_past_the_declared_size_is_refused() -> None:
    session = _session(size=100)
    with pytest.raises(uploads.UploadRejected, match="at most"):
        await uploads.write_chunk(session, 0, _body(_DATA[:101]))


def test_someone_elses_session_reads_as_missing() -> None:
    session = _session()
    with pytest.raises(uploads.UploadSessionNotFound):
        uploads.get_upload_session(session.id, "mallory")


@pytest.mark.parametrize("bad", ["../../etc", "not-a-uuid", "..", "A" * 36])
def test_an_id_that_isnt_a_uuid_never_reaches_a_path(bad: str) -> None:
    with pytest.raises(uploads.UploadSessionNotFound):
        uploads.get_upload_session(bad, "alice")


def test_a_file_over_the_limit_is_refused_at_the_start() -> None:
    with pytest.raises(uploads.UploadRejected):
        uploads.create_session("alice", "a.mp4", 101, 100, {})


@pytest.mark.asyncio
async def test_handing_off_before_every_byte_arrived_says_how_far_it_got() -> None:
    session = await uploads.write_chunk(_session(), 0, _body(_DATA[:100]))
    with pytest.raises(uploads.UploadOffsetMismatch):
        await uploads.begin_handoff(session)


@pytest.mark.asyncio
async def test_two_handoffs_cant_both_start() -> None:
    session = await uploads.begin_handoff(await _send_all(_session()))
    with pytest.raises(uploads.UploadRejected):
        await uploads.begin_handoff(session)


@pytest.mark.asyncio
async def test_the_file_goes_only_after_the_handoff_is_recorded_and_stays_after_a_failure() -> None:
    session = await uploads.begin_handoff(await _send_all(_session()))
    uploads.record_handoff_failure(session, "whisper down")
    assert uploads.staged_path(session).exists()
    session = await uploads.begin_handoff(uploads.get_upload_session(session.id, "alice"))
    uploads.record_handoff(session, {"document_id": "d"})
    stored = uploads.get_upload_session(session.id, "alice")
    assert stored.state == "done" and stored.result == {"document_id": "d"}
    assert not uploads.staged_path(session).exists()


@pytest.mark.asyncio
async def test_a_handoff_whose_worker_went_away_can_be_tried_again_later(monkeypatch) -> None:
    session = await uploads.begin_handoff(await _send_all(_session()))
    assert uploads.expired_sessions() == []
    monkeypatch.setattr(uploads, "SESSION_TTL_S", 0)
    time.sleep(0.01)
    assert [s.id for s in uploads.expired_sessions()] == [session.id]
    assert (await uploads.begin_handoff(session)).state == "handing_off"


@pytest.mark.asyncio
async def test_an_abandoned_session_stops_taking_chunks_and_is_listed_not_deleted(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(uploads, "SESSION_TTL_S", 0)
    time.sleep(0.01)
    with pytest.raises(uploads.UploadRejected, match="expired"):
        await uploads.write_chunk(session, 0, _body(b"x"))
    assert [s.id for s in uploads.expired_sessions()] == [session.id]
    assert uploads.staged_path(session).exists()


def test_cancelling_removes_what_was_staged() -> None:
    session = _session()
    uploads.cancel_session(session)
    with pytest.raises(uploads.UploadSessionNotFound):
        uploads.get_upload_session(session.id, "alice")


def test_what_a_client_sees_holds_no_path_or_owner() -> None:
    shown = uploads.describe_upload(_session())
    assert "owner" not in shown and not any("/" in str(value) for value in shown.values())


@pytest.mark.asyncio
async def test_a_declared_checksum_that_doesnt_match_fails_the_handoff() -> None:
    session = uploads.create_session("alice", "t.mp4", len(_DATA), uploads.MAX_TOTAL_BYTES, {"sha256": "0" * 64})
    session = await uploads.begin_handoff(await _send_all(session))
    with pytest.raises(uploads.UploadRejected, match="checksum_mismatch"):
        await asyncio.to_thread(uploads.verify_checksum, session)


def test_one_person_cant_hold_more_than_the_limit(monkeypatch) -> None:
    monkeypatch.setattr(uploads, "MAX_OPEN_PER_OWNER", 1)
    _session()
    with pytest.raises(uploads.UploadNoSpace):
        _session()
    uploads.create_session("bob", "b.mp4", 10, uploads.MAX_TOTAL_BYTES, {})


def test_sessions_cant_promise_more_than_the_budget(monkeypatch) -> None:
    monkeypatch.setattr(uploads, "MAX_STAGED_BYTES", 150)
    uploads.create_session("alice", "a.mp4", 100, uploads.MAX_TOTAL_BYTES, {})
    with pytest.raises(uploads.UploadNoSpace):
        uploads.create_session("bob", "b.mp4", 100, uploads.MAX_TOTAL_BYTES, {})


def test_a_disk_without_room_is_refused_at_the_start(monkeypatch) -> None:
    monkeypatch.setattr(uploads.shutil, "disk_usage", lambda _path: SimpleNamespace(free=5))
    with pytest.raises(uploads.UploadNoSpace):
        uploads.create_session("alice", "a.mp4", 100, uploads.MAX_TOTAL_BYTES, {})


@pytest.mark.asyncio
async def test_a_full_disk_mid_chunk_is_named_and_keeps_nothing(monkeypatch) -> None:
    session = _session()

    async def full():
        yield b"x"
        raise OSError(errno.ENOSPC, "No space left")

    with pytest.raises(uploads.UploadNoSpace):
        await uploads.write_chunk(session, 0, full())
    assert uploads.staged_path(session).stat().st_size == 0


@pytest.mark.asyncio
async def test_a_failed_session_expires_and_a_listed_one_can_be_removed_by_an_admin(monkeypatch) -> None:
    session = await uploads.begin_handoff(await _send_all(_session()))
    uploads.record_handoff_failure(session, "upload.handoff_failed")
    record = AsyncMock(return_value=True)
    with pytest.raises(uploads.UploadRejected, match="review list"):
        await uploads.remove_listed_session(session.id, record)
    record.assert_not_awaited()
    monkeypatch.setattr(uploads, "SESSION_TTL_S", 0)
    time.sleep(0.01)
    assert [s.id for s in uploads.expired_sessions()] == [session.id]
    await uploads.remove_listed_session(session.id, record)
    record.assert_awaited_once()
    with pytest.raises(uploads.UploadSessionNotFound):
        uploads.get_upload_session(session.id, "alice")


@pytest.mark.asyncio
async def test_a_session_being_handed_over_cant_be_removed_as_abandoned() -> None:
    session = _session()
    session.state, session.handoff_started_at = "handing_off", time.time()
    uploads._save(session)
    assert not session.expired
    with pytest.raises(uploads.UploadRejected):
        await uploads.remove_listed_session(session.id, AsyncMock(return_value=True))


@pytest.mark.asyncio
async def test_a_removal_that_cant_be_recorded_removes_nothing(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(uploads, "SESSION_TTL_S", 0)
    time.sleep(0.01)
    with pytest.raises(uploads.UploadAuditFailed):
        await uploads.remove_listed_session(session.id, AsyncMock(return_value=False))
    assert uploads.staged_path(session).exists()


@pytest.mark.asyncio
async def test_the_record_is_written_before_the_bytes_go(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(uploads, "SESSION_TTL_S", 0)
    time.sleep(0.01)
    seen = []

    async def record(_session) -> bool:
        seen.append(uploads.staged_path(session).exists())
        return True

    await uploads.remove_listed_session(session.id, record)
    assert seen == [True]
