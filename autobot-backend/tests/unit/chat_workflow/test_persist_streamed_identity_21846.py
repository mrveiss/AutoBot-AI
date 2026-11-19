# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Persisted messages keep their streamed id and creation time (#21846)."""

from __future__ import annotations

import time
from types import SimpleNamespace

from async_chat_workflow import WorkflowMessage
from chat_history.messages import MessagesMixin
from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.stream_identity import stream_identity_marker, streamed_prose_identity

EARLY = 1_700_000_000.0  # 2023-11-14, far from "now"


def _chat_mgr():
    return SimpleNamespace(_build_message_dict=lambda *a, **k: MessagesMixin._build_message_dict(None, *a, **k))


def _chunk(message_id="seg-1", display_type="response"):
    return WorkflowMessage(
        type=display_type,
        content="hel",
        timestamp=EARLY,
        metadata={"streaming": True, "display_type": display_type, "message_id": message_id},
    )


def test_build_message_dict_uses_supplied_id_and_time():
    msg = MessagesMixin._build_message_dict(
        None, "assistant", "x", "response", None, None, message_id="abc", created_at=EARLY
    )
    assert msg["id"] == "abc"
    assert msg["timestamp"] == time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(EARLY))


def test_build_message_dict_defaults_are_unchanged():
    msg = MessagesMixin._build_message_dict(None, "assistant", "x", "response", None, None)
    assert len(msg["id"]) == 36 and msg["timestamp"][:4] == time.strftime("%Y")


def test_marker_only_for_first_streamed_response_chunk():
    seen: list = []
    first = stream_identity_marker(_chunk(), 1, seen)
    assert first is not None and first.metadata["message_id"] == "seg-1" and first.timestamp == EARLY
    seen.append(first)
    assert stream_identity_marker(_chunk(), 1, seen) is None
    assert stream_identity_marker(_chunk(display_type="thought"), 1, []) is None


def test_final_reply_entry_carries_streamed_identity():
    marker = stream_identity_marker(_chunk("seg-9"), 1, [])
    streamed_id, streamed_at = streamed_prose_identity([marker])
    entry = ChatWorkflowManager._build_final_response_entry(
        None, _chat_mgr(), "hello", [], iteration=1, streamed=(streamed_id, streamed_at)
    )
    assert entry["id"] == "seg-9"
    assert entry["timestamp"] == time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(EARLY))


def test_no_marker_falls_back_to_fresh_identity():
    assert streamed_prose_identity([]) == (None, None)


def test_several_streamed_segments_in_one_iteration_persist_under_the_last_ones_identity():
    markers = [stream_identity_marker(_chunk("seg-1"), 1, []), stream_identity_marker(_chunk("seg-2"), 1, [])]
    streamed_id, _ = streamed_prose_identity(markers)
    assert streamed_id == "seg-2"
