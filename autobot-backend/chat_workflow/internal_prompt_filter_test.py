# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for Issue #716 / #11867 internal-prompt-echo filtering.

Proves:
  (a) the internal-prompt filter now runs at the production final-message yield
      point (``_execute_llm_workflow`` -> ``_persist_conversation``) — an echo
      that leaked on base is stripped;
  (b) normal assistant output passes through byte-for-byte unchanged;
  (c) the consolidated canonical filter matches the union of BOTH previously
      duplicated implementations' patterns (the 6th ``---CRITICAL---`` pattern
      lived only in models.py; manager.py had 5).
"""

import pytest

from chat_workflow.manager import ChatWorkflowManager
from chat_workflow.models import StreamingMessage, filter_internal_prompts

# A representative internal continuation prompt the LLM echoes back. Contains
# markers matching multiple canonical patterns.
ECHO = (
    "**CRITICAL MULTI-STEP TASK INSTRUCTIONS**\n" "You must keep going until the task is done.\n" "**YOUR RESPONSE:**"
)

# The genuine, user-facing answer the model produced after the echo.
REAL_ANSWER = "Here is the summary you asked for: the deploy succeeded."


class TestCanonicalFilter:
    """(b) + (c): behaviour of the consolidated canonical filter."""

    def test_normal_message_unchanged_byte_for_byte(self):
        """Legitimate assistant output is returned identical (no strip/collapse)."""
        text = "  Hello!\n\nHere is my answer.\n  "
        assert filter_internal_prompts(text) == text

    def test_normal_message_with_triple_newlines_unchanged(self):
        """No pattern match => untouched, even with blank runs (safer than base)."""
        text = "Line one.\n\n\n\nLine two."
        assert filter_internal_prompts(text) == text

    def test_strips_internal_prompt_echo(self):
        """A genuine echo is removed, leaving the real answer."""
        out = filter_internal_prompts(f"{ECHO}\n\n{REAL_ANSWER}")
        assert "CRITICAL MULTI-STEP" not in out
        assert "YOUR RESPONSE" not in out
        assert REAL_ANSWER in out

    def test_union_includes_multi_step_progress_marker(self):
        """Pattern shared by both old impls."""
        text = "User is in the middle of a multi-step task. 3 step(s) have been completed."
        assert filter_internal_prompts(text) == ""

    def test_union_includes_original_user_request_marker(self):
        text = "**ORIGINAL USER REQUEST (analyze this carefully):**"
        assert filter_internal_prompts(text) == ""

    def test_union_includes_if_more_steps_needed_marker(self):
        text = "**IF MORE STEPS NEEDED** then emit `<TOOL_CALL"
        assert filter_internal_prompts(text) == ""

    def test_union_includes_models_only_dashed_critical_pattern(self):
        """The 6th pattern lived ONLY in models.py on base; consolidation keeps it.

        Manager's 5-pattern list never matched this shape — so on base it would
        have leaked through the (dead) manager filter. The canonical union covers
        it now.
        """
        text = "---\n**CRITICAL MULTI-STEP TASK**: do the thing\n---"
        assert filter_internal_prompts(text) == ""


class TestStreamingMessageDelegates:
    """The models.py opt-in path now uses the canonical filter."""

    def test_to_workflow_message_default_leaves_echo(self):
        """Per #1313, per-chunk streaming (default False) sends raw content."""
        msg = StreamingMessage(type="response")
        msg.stream(f"{ECHO}\n\n{REAL_ANSWER}")
        wm = msg.to_workflow_message()  # default filter_prompts=False (line ~930)
        assert "CRITICAL MULTI-STEP" in wm.content

    def test_to_workflow_message_filter_true_strips_echo(self):
        """Opt-in final-message filtering removes the echo, keeps the answer."""
        msg = StreamingMessage(type="response")
        msg.stream(f"{ECHO}\n\n{REAL_ANSWER}")
        wm = msg.to_workflow_message(filter_prompts=True)
        assert "CRITICAL MULTI-STEP" not in wm.content
        assert REAL_ANSWER in wm.content


class _FakeManager:
    """Minimal stand-in exposing only what ``_execute_llm_workflow`` touches.

    Uses the REAL ``_filter_internal_prompts`` (bound from ChatWorkflowManager)
    so the production wiring is exercised end-to-end without constructing the
    full manager (terminal tool, Redis, error boundary, ...).
    """

    def __init__(self):
        self.knowledge_service = None
        self._filter_internal_prompts = ChatWorkflowManager._filter_internal_prompts.__get__(self)
        self.persisted = {}

    async def _prepare_llm_workflow_params(self, session, message, context):
        return {}

    def _create_llm_iteration_context(self, *args, **kwargs):
        return object()

    async def _execute_llm_continuation_loop(self, ctx):
        # Model echoed the internal prompt then produced the real answer.
        yield ([f"{ECHO}\n\n{REAL_ANSWER}"], None, False)

    async def _persist_conversation(self, session_id, session, message, llm_response):
        self.persisted["conversation"] = llm_response

    async def _persist_workflow_messages(self, session_id, workflow_messages, combined_response):
        self.persisted["workflow"] = combined_response

    async def _fire_stop_hook(self, *args, **kwargs):
        return None


class TestProductionWirePoint:
    """(a): #716 filtering now runs at the production final-message yield point."""

    @pytest.mark.asyncio
    async def test_final_response_is_filtered_before_persist(self):
        fake = _FakeManager()

        gen = ChatWorkflowManager._execute_llm_workflow(
            fake,
            session_id="s1",
            session=object(),
            message="hi",
            context={},
            terminal_session_id="t1",
            workflow_messages=[],
        )
        # Drive the async generator to completion (it yields nothing here).
        async for _ in gen:
            pass

        persisted = fake.persisted["conversation"]
        # BASE (no filter at line 3040) would persist the raw join -> echo leaks.
        assert "CRITICAL MULTI-STEP" not in persisted
        assert "YOUR RESPONSE" not in persisted
        assert REAL_ANSWER in persisted
        # Both persist sinks receive the same filtered text.
        assert fake.persisted["workflow"] == persisted

    def test_raw_join_would_leak_echo_on_base(self):
        """Documents the base defect: the pre-fix expression leaks the echo."""
        raw_join = "\n\n".join([f"{ECHO}\n\n{REAL_ANSWER}"])
        assert "CRITICAL MULTI-STEP" in raw_join  # base behaviour
        assert "CRITICAL MULTI-STEP" not in filter_internal_prompts(raw_join)  # fix
