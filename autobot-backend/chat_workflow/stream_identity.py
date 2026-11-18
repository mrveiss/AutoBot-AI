# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Carry a streamed reply's id and creation time into the persisted batch (#21846).

Streaming chunks are never persisted; the completed reply is rebuilt from the
accumulated text. Without help it got a fresh uuid and the persist-time clock,
so a reload could not be matched to what was streamed. The first ``response``
chunk of an iteration leaves an internal ``segment_complete`` marker (already
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
        metadata={"completed_type": "response", "message_id": message_id, "internal": True, "iteration": iteration},
    )


def streamed_prose_identity(iter_messages: Iterable[WorkflowMessage]) -> tuple[str | None, float | None]:
    """(message_id, created_at) of the iteration's first streamed reply, or (None, None)."""
    for msg in iter_messages:
        meta = msg.metadata or {}
        if msg.type == _MARKER_TYPE and meta.get("internal") and meta.get("completed_type") == "response":
            return meta.get("message_id"), msg.timestamp
    return None, None
