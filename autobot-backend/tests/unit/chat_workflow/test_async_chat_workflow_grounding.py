# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AsyncChatWorkflow grounded generation.

Issue #10732: Inject kb_results into the LLM prompt so generation is
grounded by KB search results from _workflow_knowledge_search.

Three scenarios verified:
  (a) non-empty kb_results + grounding enabled → LLM call receives KB context
  (b) empty kb_results → prompt unchanged (no regression)
  (c) grounding disabled via config → KB context not injected
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MODULE = "async_chat_workflow"
_SVC_MODULE = "services.knowledge.service"


def _make_workflow_kb_result(content: str = "AutoBot fact", source: str = "doc-1", score: float = 0.9) -> dict:
    """Return a kb_result dict in the shape produced by _execute_kb_search."""
    return {"content": content, "source": source, "score": score, "metadata": {}}


def _make_llm_response(content: str = "answer") -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.model = "llama3"
    resp.tokens_used = 10
    resp.processing_time = 0.1
    return resp


# ---------------------------------------------------------------------------
# _build_kb_context_string
# ---------------------------------------------------------------------------


class TestBuildKbContextString:
    """Unit tests for the static _build_kb_context_string helper."""

    @pytest.fixture()
    def workflow(self):
        from async_chat_workflow import AsyncChatWorkflow

        return AsyncChatWorkflow()

    def test_empty_results_returns_empty_string(self, workflow):
        """Empty kb_results → empty string (no context injected)."""
        assert workflow._build_kb_context_string([]) == ""

    def test_results_without_content_returns_empty_string(self, workflow):
        """Results with empty/missing content field → empty string."""
        assert workflow._build_kb_context_string([{"content": "", "source": "x", "score": 0.5, "metadata": {}}]) == ""

    def test_populated_results_contain_source_n_labels(self, workflow):
        """Non-empty results produce [Source N] blocks via build_grounded_context."""
        results = [
            _make_workflow_kb_result("fact one", score=0.9),
            _make_workflow_kb_result("fact two", score=0.8),
        ]
        ctx = workflow._build_kb_context_string(results)
        assert "[Source 1]" in ctx
        assert "[Source 2]" in ctx
        assert "fact one" in ctx
        assert "fact two" in ctx

    def test_grounding_disabled_omits_instruction(self, workflow):
        """When chat_grounding_enabled is False the grounding instruction is omitted."""
        results = [_make_workflow_kb_result("fact")]
        mock_cfg = MagicMock()
        mock_cfg.chat_grounding_enabled = False
        with patch(f"{_SVC_MODULE}.config", mock_cfg):
            ctx = workflow._build_kb_context_string(results)
        assert "KNOWLEDGE CONTEXT:" in ctx
        assert "Answer the user" not in ctx


# ---------------------------------------------------------------------------
# _generate_llm_response with kb_results
# ---------------------------------------------------------------------------


class TestGenerateLlmResponseGrounding:
    """Tests that _generate_llm_response injects KB context into the system message."""

    @pytest.fixture()
    def workflow(self):
        from async_chat_workflow import AsyncChatWorkflow

        return AsyncChatWorkflow()

    async def test_kb_context_reaches_llm_when_results_present(self, workflow):
        """(a) Non-empty kb_results + grounding enabled → LLM receives KB context."""
        kb_results = [_make_workflow_kb_result("grounding fact")]
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(return_value=_make_llm_response())

        await workflow._generate_llm_response("question", mock_llm, kb_results)

        call_messages = mock_llm.chat_completion.call_args[0][0]
        system_msg = next(m for m in call_messages if m.role == "system")
        assert "[Source 1]" in system_msg.content
        assert "grounding fact" in system_msg.content

    async def test_no_kb_context_when_results_empty(self, workflow):
        """(b) Empty kb_results → system prompt unchanged (no [Source N] blocks)."""
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(return_value=_make_llm_response())

        await workflow._generate_llm_response("question", mock_llm, [])

        call_messages = mock_llm.chat_completion.call_args[0][0]
        system_msg = next(m for m in call_messages if m.role == "system")
        assert "[Source" not in system_msg.content
        assert "KNOWLEDGE CONTEXT" not in system_msg.content

    async def test_no_kb_context_when_grounding_disabled(self, workflow):
        """(c) Grounding disabled via config → KB context not injected."""
        kb_results = [_make_workflow_kb_result("grounding fact")]
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(return_value=_make_llm_response())
        mock_cfg = MagicMock()
        mock_cfg.chat_grounding_enabled = False

        with patch(f"{_SVC_MODULE}.config", mock_cfg):
            await workflow._generate_llm_response("question", mock_llm, kb_results)

        call_messages = mock_llm.chat_completion.call_args[0][0]
        system_msg = next(m for m in call_messages if m.role == "system")
        # [Source N] labels still present; grounding *instruction* is omitted
        assert "Answer the user's question using the knowledge sources" not in system_msg.content
        assert "[Source 1]" in system_msg.content


# ---------------------------------------------------------------------------
# _workflow_llm_generate threads kb_results through to _generate_llm_response
# ---------------------------------------------------------------------------


class TestWorkflowLlmGeneratePassesKbResults:
    """Tests that _workflow_llm_generate forwards kb_results to _generate_llm_response."""

    @pytest.fixture()
    def workflow(self):
        from async_chat_workflow import AsyncChatWorkflow

        return AsyncChatWorkflow()

    async def test_kb_results_forwarded_to_generate(self, workflow):
        """kb_results passed to _workflow_llm_generate reach _generate_llm_response."""
        kb_results = [_make_workflow_kb_result("forwarded fact")]
        fake_response = _make_llm_response("ok")

        with patch.object(workflow, "_generate_llm_response", new=AsyncMock(return_value=fake_response)) as mock_gen:
            await workflow._workflow_llm_generate("q", MagicMock(), [], kb_results)

        _args, _kwargs = mock_gen.call_args
        # Third positional arg is kb_results
        assert _args[2] == kb_results

    async def test_empty_kb_results_passed_when_none(self, workflow):
        """When kb_results is None, _generate_llm_response receives an empty list."""
        fake_response = _make_llm_response("ok")

        with patch.object(workflow, "_generate_llm_response", new=AsyncMock(return_value=fake_response)) as mock_gen:
            await workflow._workflow_llm_generate("q", MagicMock(), [], None)

        _args, _kwargs = mock_gen.call_args
        assert _args[2] == []
