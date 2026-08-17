# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for #14248 — a session whose ``os.stat`` fails must not vanish from
``list_sessions_fast`` without a trace.

Before the fix, ``_build_session_entry`` caught the stat failure, logged a
generic ``"Error reading file stats for %s: %s"`` keyed on the *filename*, and
returned ``None`` — which the caller silently dropped from the sessions list.
An operator reading the log could not tell "this conversation is unreadable"
from "no such conversation ever existed", and skill distillation (which reads
``list_sessions_fast`` for its pending set) never saw the session at all, so it
was never reported as skipped.

These tests drive the real listing path (a real ``SessionListingMixin`` over
real files on disk, with ``os.stat`` failing for exactly one of them) rather
than stubbing ``_build_session_entry`` or the lister — the defect was in the
composition of the real path, and a stubbed lister would hide it.
"""

import json
import logging
import os

import pytest

from chat_history.session_listing import SessionListingMixin


class _StubManager(SessionListingMixin):
    """Minimal manager exercising the real listing path on real disk."""

    def __init__(self, chats_directory: str):
        self._chats_directory = chats_directory

    def _get_chats_directory(self) -> str:
        return self._chats_directory


def _write_chat_file(tmp_path, chat_id: str) -> str:
    chat_path = tmp_path / f"{chat_id}_chat.json"
    chat_path.write_text(
        json.dumps({"name": f"Chat {chat_id}", "messages": []}),
        encoding="utf-8",
    )
    return str(chat_path)


@pytest.fixture()
def manager(tmp_path):
    return _StubManager(str(tmp_path))


class TestStatFailureIsVisible:
    """A stat failure must be logged and distinguishable from "does not exist" (#14248)."""

    @pytest.mark.asyncio
    async def test_unreadable_session_is_logged_with_its_id(self, manager, tmp_path, monkeypatch, caplog):
        good_id = "sess-good"
        bad_id = "sess-bad-stat"
        _write_chat_file(tmp_path, good_id)
        bad_path = _write_chat_file(tmp_path, bad_id)

        real_stat = os.stat

        def flaky_stat(path, *args, **kwargs):
            if os.fspath(path) == bad_path:
                raise PermissionError(f"simulated stat failure for {path}")
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr(os, "stat", flaky_stat)

        with caplog.at_level(logging.ERROR, logger="chat_history.session_listing"):
            sessions = await manager.list_sessions_fast()

        session_ids = {s["id"] for s in sessions}
        assert good_id in session_ids

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "stat failure produced no log record — silent drop reproduced"
        # Requires the session id in a "session <id>" position, not merely as a
        # filename substring — chat_id is always a substring of its own
        # filename by construction (_extract_chat_id_from_filename strips a
        # fixed affix), so a looser "id in message" check would still pass
        # against the pre-fix message ("Error reading file stats for
        # <filename>: ...") and catch nothing.
        assert any(
            f"session {bad_id} " in r.getMessage() for r in error_records
        ), "log record does not name the failing session id in a 'session <id>' position"

    @pytest.mark.asyncio
    async def test_unreadable_session_wording_differs_from_not_found(self, manager, tmp_path, monkeypatch, caplog):
        bad_id = "sess-bad-stat-2"
        bad_path = _write_chat_file(tmp_path, bad_id)

        real_stat = os.stat

        def flaky_stat(path, *args, **kwargs):
            if os.fspath(path) == bad_path:
                raise OSError(f"simulated stat failure for {path}")
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr(os, "stat", flaky_stat)

        with caplog.at_level(logging.ERROR, logger="chat_history.session_listing"):
            await manager.list_sessions_fast()

        [record] = [r for r in caplog.records if bad_id in r.getMessage()]
        message = record.getMessage()
        # "not found" is the phrasing used elsewhere in chat_history for a
        # session that never existed (see session.py). A stat failure on a
        # file that IS present must not read the same way.
        assert "not found" not in message.lower()
        assert "exists" in message.lower()

    @pytest.mark.asyncio
    async def test_stat_failure_still_excludes_from_this_pass(self, manager, tmp_path, monkeypatch):
        """Matches the malformed-timestamp precedent: loud, then excluded — not
        silently kept with garbage data, and not silently dropped."""
        bad_id = "sess-bad-stat-3"
        bad_path = _write_chat_file(tmp_path, bad_id)

        real_stat = os.stat

        def flaky_stat(path, *args, **kwargs):
            if os.fspath(path) == bad_path:
                raise OSError("simulated stat failure")
            return real_stat(path, *args, **kwargs)

        monkeypatch.setattr(os, "stat", flaky_stat)

        sessions = await manager.list_sessions_fast()

        assert bad_id not in {s["id"] for s in sessions}
