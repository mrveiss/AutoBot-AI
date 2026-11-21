# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A graph entered without a turn's input is reported, never indexed into (#21939)."""

from __future__ import annotations

from typing import Any, Callable, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

REQUIRED_TURN_KEYS = ("session_id", "user_message")
NO_TURN_MESSAGE = "Nothing to run: the chat state carries no turn input"


def missing_turn_state(state: Dict[str, Any], stream_cb: Callable | None) -> Dict[str, Any] | None:
    """The error update for a state lacking the turn's input, or ``None`` when it is complete.

    A resume reaches the entry node with an empty state when nothing was waiting to resume; the route refuses that
    first, and this is the node's own answer should any other path get there.
    """
    missing = [key for key in REQUIRED_TURN_KEYS if key not in state]
    if not missing:
        return None
    logger.error(
        "initialize_session entered without %s; the graph has no turn to start",
        ", ".join(missing),
    )
    error_msg = {"type": "error", "content": NO_TURN_MESSAGE}
    if stream_cb:
        stream_cb(error_msg)
    return {"error": NO_TURN_MESSAGE, "workflow_messages": [error_msg]}
