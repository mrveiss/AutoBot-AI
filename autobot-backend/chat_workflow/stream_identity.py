# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Carry a streamed reply's id and creation time into the persisted batch (#21846).

Streaming chunks are never persisted; the completed reply is rebuilt from the
accumulated text. Without help it got a fresh uuid and the persist-time clock,
so a reload could not be matched to what was streamed. The first ``response``
chunk of each streamed segment leaves an internal ``segment_complete`` marker (already
skipped by the persister) holding the streamed ``message_id`` and chunk time.
"""

from __future__ import annotations

from typing import Any, Iterable

from async_chat_workflow import WorkflowMessage

_MARKER_TYPE = "segment_complete"


def stream_identity_marker(chunk: Any, iteration: int, existing: list) -> WorkflowMessage | None:
    """Marker for the first streamed ``response`` chunk of a message id (not already in *existing*), else None."""
    meta = getattr(chunk, "metadata", None) or {}
    message_id = meta.get("message_id")
    if not meta.get("streaming") or meta.get("display_type") != "response" or not message_id:
        return None
    if any(m.type == _MARKER_TYPE and (m.metadata or {}).get("message_id") == message_id for m in existing):
        return None
    return WorkflowMessage(
        type=_MARKER_TYPE,
        content="",
        timestamp=chunk.timestamp,
        metadata={
            "completed_type": "response",
            "message_id": message_id,
            "internal": True,
            "iteration": iteration,
            "model": meta.get("model"),  # #21881: the model that produced this chunk
        },
    )


def streamed_prose_identity(iter_messages: Iterable[WorkflowMessage]) -> tuple[str | None, float | None]:
    """(message_id, created_at) of the iteration's LAST streamed reply segment, or (None, None).

    An iteration can stream several reply segments, each with its own id. The persisted reply is one message
    holding all the prose, so it takes the last segment's identity: the one a reload sorts and matches by, and the
    one that does not leave an earlier streamed segment standing next to a second copy of the same text (#21846).
    With no marker the time is ``prose_time_before`` the iteration's own steps.
    """
    iter_messages = list(iter_messages)
    found: tuple[str | None, float | None] = (None, None)
    for msg in iter_messages:
        meta = msg.metadata or {}
        if msg.type == _MARKER_TYPE and meta.get("internal") and meta.get("completed_type") == "response":
            found = (meta.get("message_id"), msg.timestamp)
    if found[1] is None:  # no streamed marker: the prose was said before the steps it introduced ran (#21904)
        found = (found[0], prose_time_before(iter_messages))
    return found


def streamed_prose_model(iter_messages: Iterable[WorkflowMessage]) -> str | None:
    """The model the iteration's LAST streamed reply segment came from (#21881), or None when none is recorded."""
    found: str | None = None
    for msg in iter_messages:
        meta = msg.metadata or {}
        if msg.type == _MARKER_TYPE and meta.get("internal") and meta.get("completed_type") == "response":
            found = meta.get("model") or found
    return found


def prose_time_before(iter_messages: Iterable[WorkflowMessage]) -> float | None:
    """The earliest creation time among an iteration's own messages, or None when it has none (#21904).

    An iteration's prose with no streamed marker is built at persist time, after the tool steps it introduced ran.
    Stamped at the earliest of those steps instead, it sorts before them, as it was said before they ran.
    """
    times = [m.timestamp for m in iter_messages if m.type != _MARKER_TYPE and m.timestamp]
    return min(times) if times else None
