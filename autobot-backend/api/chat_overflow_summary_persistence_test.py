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


# ---------------------------------------------------------------------------
# #14066 composed summaries specifically.
#
# The tests above prove a *prose* summary survives. #14066 made the summary
# three things rather than one: the model's prose, a deterministic state block
# extracted from the tool calls, and the user's own turns carried verbatim. Two
# of those exist precisely so a bad summarisation turn cannot take the session's
# state with it — which only holds if they reach the model, not merely the
# status dict.
#
# Between #14066 merging and #14341 landing, they did not: the composed summary
# was built correctly and then persisted with an empty body. Nothing failed,
# because no test followed a composed summary past the function that built it.
# ---------------------------------------------------------------------------


def _composed_summary() -> str:
    """A real `_create_summary` result, built by the real producer."""
    from unittest.mock import AsyncMock

    from chat_history.context_overflow import ContextOverflowProtection

    protection = ContextOverflowProtection()
    protection.summarizer.summarize_messages = AsyncMock(return_value="The user asked for a release.")
    protection.tracker.reset_session = AsyncMock()
    protection.tracker.add_message_tokens = AsyncMock()

    # Both tool calls sit before the compaction boundary on purpose. The state
    # block describes the region being compacted *away*; work in the retained
    # half is still present as real history and needs no carrying. An earlier
    # draft of this fixture put the command after the boundary and then asserted
    # it survived — the assertion was wrong, not the code.
    history = [
        {"role": "user", "content": "never deploy straight to prod"},
        {
            "role": "assistant",
            "tool_calls": [{"function": {"name": "write_file", "arguments": '{"path": "deploy/release.yaml"}'}}],
        },
        {"role": "tool", "content": "written"},
        {
            "role": "assistant",
            "tool_calls": [{"function": {"name": "execute_command", "arguments": '{"command": "make release"}'}}],
        },
        {"role": "tool", "content": "exit status 0"},
        {"role": "user", "content": "now ship it"},
        {"role": "assistant", "content": "shipped"},
        {"role": "user", "content": "thanks"},
        {"role": "assistant", "content": "welcome"},
        {"role": "user", "content": "one more thing"},
        {"role": "assistant", "content": "go on"},
        {"role": "user", "content": "done"},
    ]
    return asyncio.run(protection._create_summary("session-1", history, "gpt-4"))


def test_the_composed_summary_really_carries_state_the_prose_does_not() -> None:
    """Guards the fixture: if composition regressed, the tests below would pass vacuously."""
    composed = _composed_summary()

    assert "deploy/release.yaml" in composed, "the extracted state block is missing from the summary"
    assert "never deploy straight to prod" in composed, "the user's own instruction was summarised away"
    assert "deploy/release.yaml" not in "The user asked for a release."


def test_the_extracted_state_block_survives_persistence() -> None:
    """A file path is mechanically derived, so its absence is unambiguous.

    A non-empty check passes on prose alone; this does not.
    """
    persisted = _to_persisted_message(asyncio.run(create_summary_message(_composed_summary())), "context_summary")

    assert "deploy/release.yaml" in message_text(persisted)
    assert "make release" in message_text(persisted)


def test_the_users_own_instruction_survives_persistence() -> None:
    """The constraint a user stated once is the thing compaction most easily loses."""
    persisted = _to_persisted_message(asyncio.run(create_summary_message(_composed_summary())), "context_summary")

    assert "never deploy straight to prod" in message_text(persisted)


def test_a_composed_summary_reaches_the_model_on_the_next_turn() -> None:
    """End to end: compose -> persist -> rebuild context.

    This is the assertion that would have caught #14066 shipping inert. It
    follows the summary all the way to what `_build_llm_context` hands the
    provider, rather than stopping at the dict the writer was given.
    """
    persisted = _to_persisted_message(asyncio.run(create_summary_message(_composed_summary())), "context_summary")

    context = _build_llm_context([persisted], _incoming(), _manager(), None)

    bodies = " ".join(m["content"] for m in context)
    assert "deploy/release.yaml" in bodies, "the state block never reached the model"
    assert "never deploy straight to prod" in bodies, "the user's instruction never reached the model"
