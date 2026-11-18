# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13856 — session-listing timestamps must be unambiguous on the wire.

``_build_session_entry`` and ``_build_orphaned_session_dict`` used
``datetime.fromtimestamp(...).isoformat()`` with no ``tz=``. That produces a
**naive local** string with no offset, which every ``parse_utc_iso`` consumer
then tags as UTC — so the value is wrong by the host's UTC offset, and the sign
of the error flips depending on which side of UTC the host sits.

The convention followed here is the codebase's own, not an invention: the
``+00:00`` ISO-8601 form canonicalised by ``autobot_shared.time_utils`` (#5169)
and already used by every ``fromtimestamp(..., tz=timezone.utc)`` producer in
the tree. Riga time is a *display* convention for humans; a serialised value
carries UTC and the client renders it.

Every test here forces a non-UTC process timezone, because on a UTC host a
dropped ``tz=`` is invisible: the naive string and the aware string name the
same instant and a host-local assertion passes either way.
"""

import ast
import os
import time
from datetime import datetime
from pathlib import Path

import pytest

from autobot_shared.time_utils import parse_utc_iso
from chat_history.session_listing import SessionListingMixin

# UTC+14 — the largest standard offset there is, so a dropped tz cannot be
# mistaken for rounding, and the sign is unambiguous.
_NON_UTC_ZONE = "Pacific/Kiritimati"
_SOURCE = Path(__file__).with_name("session_listing.py")


class _StubManager(SessionListingMixin):
    """Minimal manager exercising the real listing path on real disk."""

    def __init__(self, chats_directory: str):
        self._chats_directory = chats_directory

    def _get_chats_directory(self) -> str:
        return self._chats_directory


@pytest.fixture()
def non_utc_tz(monkeypatch):
    """Run the body in a process timezone far from UTC, then restore."""
    monkeypatch.setenv("TZ", _NON_UTC_ZONE)
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _write_chat(tmp_path, chat_id: str) -> str:
    path = tmp_path / f"{chat_id}_chat.json"
    path.write_text('{"name": "c", "messages": []}', encoding="utf-8")
    return str(path)


class TestInstrument:
    """Known positive: prove the timezone fixture actually bites (#15953).

    Without this, a fixture that silently failed to change the process zone
    would make every assertion below pass against the unfixed code.
    """

    def test_a_dropped_tz_is_detectable_in_this_fixture(self, non_utc_tz, tmp_path):
        path = Path(_write_chat(tmp_path, "control"))
        mtime = path.stat().st_mtime
        naive = datetime.fromtimestamp(mtime).isoformat()  # the pre-#13856 shape
        assert parse_utc_iso(naive).timestamp() != pytest.approx(mtime, abs=1.0), (
            "the process timezone is still UTC — every assertion in this module " "would pass against the unfixed code"
        )


class TestSessionEntryTimestamps:
    """``list_sessions_fast`` entries round-trip to the correct instant."""

    @pytest.mark.asyncio
    async def test_updated_at_round_trips_through_parse_utc_iso(self, non_utc_tz, tmp_path):
        chat_path = _write_chat(tmp_path, "sess-a")
        mtime = os.stat(chat_path).st_mtime

        entry = await _StubManager(str(tmp_path))._build_session_entry("sess-a", chat_path, "sess-a_chat.json")

        assert parse_utc_iso(entry["updatedAt"]).timestamp() == pytest.approx(mtime, abs=0.001)
        assert parse_utc_iso(entry["lastModified"]).timestamp() == pytest.approx(mtime, abs=0.001)

    @pytest.mark.asyncio
    async def test_the_string_itself_carries_an_offset(self, non_utc_tz, tmp_path):
        """``parse_utc_iso`` tags a naive string as UTC, so it alone cannot tell
        "aware UTC" from "naive, assumed UTC". ``fromisoformat`` can."""
        chat_path = _write_chat(tmp_path, "sess-b")

        entry = await _StubManager(str(tmp_path))._build_session_entry("sess-b", chat_path, "sess-b_chat.json")

        for field in ("createdAt", "createdTime", "updatedAt", "lastModified"):
            assert datetime.fromisoformat(entry[field]).tzinfo is not None, f"{field} has no offset"
            assert datetime.fromisoformat(entry[field]).utcoffset().total_seconds() == 0, f"{field} is not UTC"

    @pytest.mark.asyncio
    async def test_iso_field_and_epoch_field_name_the_same_instant(self, non_utc_tz, tmp_path):
        """#13948's ``updatedAtEpoch`` and the ISO string must not disagree.

        The skill-distillation cursor (#13948) reads ``updatedAtEpoch`` first and
        falls back to parsing ``updatedAt``. While the string was naive local the
        two paths resolved to instants an offset apart, so which one a session was
        compared under decided whether it was re-distilled.
        """
        chat_path = _write_chat(tmp_path, "sess-c")

        entry = await _StubManager(str(tmp_path))._build_session_entry("sess-c", chat_path, "sess-c_chat.json")

        assert parse_utc_iso(entry["updatedAt"]).timestamp() == pytest.approx(entry["updatedAtEpoch"], abs=0.001)

    def test_orphaned_session_dict_uses_the_same_convention(self, non_utc_tz, tmp_path):
        chat_path = _write_chat(tmp_path, "sess-d")
        stat = os.stat(chat_path)

        entry = _StubManager(str(tmp_path))._build_orphaned_session_dict("sess-d", stat)

        assert parse_utc_iso(entry["updatedAt"]).timestamp() == pytest.approx(stat.st_mtime, abs=0.001)
        assert datetime.fromisoformat(entry["createdAt"]).tzinfo is not None


def _naive_fromtimestamp_calls(source: str) -> list[int]:
    """Line numbers of ``fromtimestamp(...)`` calls with no ``tz`` keyword.

    Parses the AST rather than grepping: ``grep 'tz=timezone.utc'`` is satisfied
    by this very docstring, and nine guards in this repo have been defeated that
    way. ``test_detector_ignores_prose`` is the contrast fixture for it.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "fromtimestamp":
            continue
        if not any(kw.arg == "tz" for kw in node.keywords):
            found.append(node.lineno)
    return found


class TestNoNaiveProducerRemains:
    """#13856 is a defect *class* in one file — a new call site must not reopen it."""

    def test_detector_finds_a_known_naive_call(self):
        """Positive control: the detector is not simply returning an empty list."""
        assert _naive_fromtimestamp_calls("datetime.fromtimestamp(x).isoformat()") == [1]

    def test_detector_ignores_prose(self):
        """Contrast fixture: the required string present ONLY in a comment and a
        docstring must not satisfy the check."""
        prose_only = '"""Always call fromtimestamp(x, tz=timezone.utc)."""\n' "# use tz=timezone.utc here\n" "pass\n"
        assert _naive_fromtimestamp_calls(prose_only) == []
        commented_out = "# datetime.fromtimestamp(x).isoformat()\npass\n"
        assert _naive_fromtimestamp_calls(commented_out) == []

    def test_session_listing_has_no_naive_fromtimestamp(self):
        offenders = _naive_fromtimestamp_calls(_SOURCE.read_text(encoding="utf-8"))
        assert offenders == [], f"{_SOURCE.name} has fromtimestamp() without tz= at lines {offenders}"
