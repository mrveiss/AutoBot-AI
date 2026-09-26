# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/tests/test_kb_route_17022.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The KB push route reports what the push did, not what it was asked to do (#17022).

The route used to answer ``{"indexed": result.get("indexed", len(segments))}``, so a
push that returned no count at all was reported as having indexed every segment --
and while ``push_to_kb`` called a method that does not exist, that was every push it
could ever have made. It also recorded a ``kb_pushes`` row unconditionally, which is
what ``/kb/status`` shows the user as "In Knowledge Base".
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from transcriber.models import KbPushRequest
from transcriber.routes.kb import _push_outcome, kb_push

COMPLETE = {"status": "complete", "filename": "meeting.wav"}


def _result(indexed=2, duplicate=0, failed=0, added=2, already=0, missing=0, segments=None):
    return {
        "indexed": indexed,
        "duplicate": duplicate,
        "failed": failed,
        "segments": indexed + duplicate + failed if segments is None else segments,
        "fact_ids": [f"fact-{n}" for n in range(indexed + duplicate)],
        "collection": {"added": added, "already_present": already, "missing": missing},
    }


class _Db:
    """Records the one write the route makes, so an unearned row is visible."""

    def __init__(self, recording=COMPLETE):
        self._recording = recording
        self.pushes = []

    async def get_recording(self, recording_id):
        return self._recording

    async def create_kb_push(self, recording_id, collection_id, pushed_by):
        self.pushes.append((recording_id, collection_id, pushed_by))
        return len(self.pushes)


async def _call(db, result):
    with (
        patch("transcriber.routes.kb.caller_can_access", return_value=True),
        patch("transcriber.routes.kb.caller_id_of", return_value="u1"),
        patch("transcriber.routes.kb.build_segment_list", AsyncMock(return_value=[{}, {}])),
        patch("transcriber.routes.kb.push_to_kb", AsyncMock(return_value=result)),
    ):
        return await kb_push(
            recording_id=7,
            body=KbPushRequest(collection_id="col-1"),
            request=SimpleNamespace(),
            db=db,
        )


def test_every_segment_stored_and_routed_is_ok():
    assert _push_outcome(_result(), "col-1") == "ok"


def test_a_rejected_segment_makes_the_push_partial():
    assert _push_outcome(_result(indexed=1, failed=1, added=1), "col-1") == "partial"


def test_a_push_where_nothing_landed_is_a_failure():
    assert _push_outcome(_result(indexed=0, failed=2, added=0), "col-1") == "failed"


def test_a_collection_that_joined_nothing_is_not_reported_as_ok():
    """The segments are retrievable; the collection the caller named does not hold them."""
    assert _push_outcome(_result(added=0, missing=2), "col-1") == "partial"


def test_a_push_with_no_collection_asked_for_is_still_ok():
    assert _push_outcome(_result(added=0), "") == "ok"


@pytest.mark.asyncio
async def test_the_route_reports_the_counts_the_push_returned():
    db = _Db()

    body = await _call(db, _result(indexed=1, duplicate=1))

    # Two segments were sent; the answer is what came back, not len(segments).
    assert body["indexed"] == 1
    assert body["duplicate"] == 1
    assert body["failed"] == 0
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_a_push_that_stored_nothing_records_no_row():
    db = _Db()

    body = await _call(db, _result(indexed=0, failed=2, added=0))

    assert body["status"] == "failed"
    assert body["indexed"] == 0
    # /kb/status reads this table: a row here would tell the user the recording is
    # in the Knowledge Base when not one segment of it is.
    assert db.pushes == []


@pytest.mark.asyncio
async def test_a_push_that_stored_something_records_one_row():
    db = _Db()

    await _call(db, _result())

    assert db.pushes == [(7, "col-1", "u1")]
