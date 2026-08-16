# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for Issue #14341 — context-overflow summaries were

persisted with an empty body.

``chat_history/overflow_integration.py::create_summary_message`` returns the
summary under the *stored*-shape body key (``text``); ``api/chat.py``'s
``_to_persisted_message`` read only the *API*-shape key (``content``),
defaulting to ``""``. The record that landed had a valid id, sender,
timestamp and type — and no text, so the conversation the summary was meant
to replace was gone with nothing standing in for it.

These tests build the summary with the real producer
(``create_summary_message``) and read it back with the real consumers
(``_to_persisted_message`` and, for the end-to-end case, ``_build_llm_context``
— the function that turns persisted history into what the model actually
sees), rather than hand-feeding a dict already shaped like the fix's own
check.
"""

import asyncio
from unittest.mock import MagicMock

from api.chat import _build_llm_context, _to_persisted_message
from chat_history.message_schema import message_text
from chat_history.overflow_integration import create_summary_message


def _incoming(text: str = "and now?"):
    message = MagicMock()
    message.role = "user"
    message.content = text
    return message


def _manager(limit: int = 20):
    manager = MagicMock()
    manager.context_manager.get_message_limit = MagicMock(return_value=limit)
    return manager


def test_summary_round_trips_through_persistence_with_its_text_intact() -> None:
    """create_summary_message -> _to_persisted_message must not drop the body."""
    summary = asyncio.run(create_summary_message("earlier: deployed the release, then rolled back"))

    persisted = _to_persisted_message(summary, "context_summary")

    # Read the way a consumer does (message_schema), not by inspecting the
    # dict the writer happened to produce.
    assert message_text(persisted) == "earlier: deployed the release, then rolled back"


def test_summary_producer_really_does_use_the_stored_shape_key() -> None:
    """Precondition: this cannot pass because the mismatch is already absent."""
    summary = asyncio.run(create_summary_message("some earlier history"))

    assert "content" not in summary, "producer already writes the API-shape key"
    assert summary["text"] == "some earlier history"


def test_a_subsequent_context_build_contains_the_summary_text() -> None:
    """End to end: overflow triggers, summary persists, and a later context
    build (the real _build_llm_context, not a mock) still contains it."""
    summary = asyncio.run(create_summary_message("condensed: user asked about deploys, agent explained code-sync"))
    persisted = _to_persisted_message(summary, "context_summary")

    context = _build_llm_context([persisted], _incoming(), _manager(), None)

    assert any("condensed: user asked about deploys" in m["content"] for m in context[:-1])


def test_persisted_summary_is_not_empty() -> None:
    """The acceptance criterion in the issue's own words: non-empty, read the
    way a consumer reads it."""
    summary = asyncio.run(create_summary_message("non-trivial summary body"))

    persisted = _to_persisted_message(summary, "context_summary")

    assert message_text(persisted) != ""
