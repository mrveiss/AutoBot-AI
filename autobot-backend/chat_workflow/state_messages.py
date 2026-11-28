# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rebuild a ``WorkflowMessage`` from the graph's plain-dict state entry (#21904, #21846).

The graph keeps ``WorkflowMessage.to_dict()`` output in its state. Rebuilding a message from only its type,
content and metadata gave it a fresh id and the persist-time clock, so every tool step was stored with the
time it was persisted and a later-built prose entry sorted after them. The rebuilt message keeps the id and
the epoch creation time the dict carries.
"""

from __future__ import annotations

from typing import Any, Dict

from async_chat_workflow import WorkflowMessage


def workflow_message_from_state(entry: Dict[str, Any]) -> WorkflowMessage:
    """The ``WorkflowMessage`` a graph-state dict describes, with its own id and creation time when it has them."""
    extra: Dict[str, Any] = {}
    if entry.get("id"):
        extra["id"] = entry["id"]
    created_at = entry.get("created_at")
    if isinstance(created_at, (int, float)) and not isinstance(created_at, bool):
        extra["timestamp"] = float(created_at)
    return WorkflowMessage(
        type=entry.get("type", "response"),
        content=entry.get("content", ""),
        metadata=entry.get("metadata", {}),
        **extra,
    )
