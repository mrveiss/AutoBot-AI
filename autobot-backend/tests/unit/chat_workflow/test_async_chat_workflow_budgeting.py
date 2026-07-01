# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AsyncChatWorkflow KB context budgeting via ContextWindowManager.

Issue #10735: _budget_kb_context must apply ContextWindowManager compression
before injecting KB results into the system prompt, mirroring llm_handler.py
lines 793-823.

Scenarios:
  (a) small kb_results (below threshold) → context returned unchanged (no truncation)
  (b) oversized kb_results (above threshold) → compress_kb_results invoked; context bounded
  (c) grounding disabled → _budget_kb_context returns empty string (no injection)
  (d) empty kb_results → empty string, no manager instantiated
"""

from unittest.mock import AsyncMock, MagicMock, patch

_MODULE = "async_chat_workflow"
_CWM_MODULE = "context_window_manager"
_SVC_MODULE = "services.knowledge.service"
_COMP_MODULE = "services.memory.compression"

# Lazy imports in _budget_kb_context are patched at their source module so
# the local `from X import Y` inside the function picks up the mock.
_CWM_CLASS = f"{_CWM_MODULE}.ContextWindowManager"
_COMP_CLASS = f"{_COMP_MODULE}.ContextCompressionService"


def _make_kb_result(content: str = "AutoBot fact", source: str = "doc-1", score: float = 0.9) -> dict:
    return {"content": content, "source": source, "score": score, "metadata": {}}


def _make_llm_response(content: str = "answer") -> MagicMock:
    resp = MagicMock()
    resp.content = content
    resp.model = "llama3"
    resp.tokens_used = 10
    resp.processing_time = 0.1
    return resp


# ---------------------------------------------------------------------------
# _budget_kb_context: no-compression paths
# ---------------------------------------------------------------------------


class TestBudgetKbContextSmallResults:
    """Small kb_results stay below threshold → context unchanged."""

    async def test_empty_results_returns_empty_string(self):
        """(d) Empty kb_results → empty string; ContextWindowManager never instantiated."""
        from async_chat_workflow import AsyncChatWorkflow

        with patch(_CWM_CLASS, side_effect=AssertionError("should not be called")):
            result = await AsyncChatWorkflow._budget_kb_context([])

        assert result == ""

    async def test_small_results_not_compressed(self):
        """(a) Results below token threshold → compress_kb_results NOT invoked."""
        from async_chat_workflow import AsyncChatWorkflow

        kb_results = [_make_kb_result("short fact")]

        mock_cwm = MagicMock()
        mock_cwm.estimate_tokens.return_value = 10  # well under any threshold
        mock_cwm.get_max_history_tokens.return_value = 4096
        mock_cwm.async_should_compress = AsyncMock(return_value=False)
        mock_cwm.config = {"models": {}}

        with patch(_CWM_CLASS, return_value=mock_cwm):
            result = await AsyncChatWorkflow._budget_kb_context(kb_results)

        # compress_kb_results should NOT have been called (no ContextCompressionService)
        mock_cwm.async_should_compress.assert_called_once()
        assert "short fact" in result
        assert "[Source 1]" in result

    async def test_grounding_disabled_omits_instruction_but_returns_context(self):
        """(c) Grounding instruction omitted when chat_grounding_enabled=False.

        build_grounded_context still returns the [Source N] block with content —
        the grounding *instruction* (Answer the user…) is the only thing suppressed.
        """
        from async_chat_workflow import AsyncChatWorkflow

        kb_results = [_make_kb_result("some fact")]
        mock_cfg = MagicMock()
        mock_cfg.chat_grounding_enabled = False

        mock_cwm = MagicMock()
        mock_cwm.estimate_tokens.return_value = 5
        mock_cwm.get_max_history_tokens.return_value = 4096
        mock_cwm.async_should_compress = AsyncMock(return_value=False)
        mock_cwm.config = {"models": {}}

        with patch(f"{_SVC_MODULE}.config", mock_cfg), patch(_CWM_CLASS, return_value=mock_cwm):
            result = await AsyncChatWorkflow._budget_kb_context(kb_results)

        # Content is still returned; only the grounding instruction is omitted.
        assert "some fact" in result
        assert "Answer the user" not in result


# ---------------------------------------------------------------------------
# _budget_kb_context: compression path
# ---------------------------------------------------------------------------


class TestBudgetKbContextOversized:
    """Oversized kb_results → compress_kb_results invoked; returned context is bounded."""

    async def test_oversized_results_compress_invoked(self):
        """(b) Token count exceeds threshold → compress_kb_results called and result rebuilt."""
        from async_chat_workflow import AsyncChatWorkflow

        kb_results = [
            _make_kb_result("fact A" * 1000, score=0.9),
            _make_kb_result("fact B" * 1000, score=0.7),
            _make_kb_result("fact C" * 1000, score=0.5),
        ]
        trimmed = [kb_results[0]]  # compression keeps only highest-score result

        mock_cwm = MagicMock()
        mock_cwm.estimate_tokens.side_effect = lambda text: len(text) // 4
        mock_cwm.get_max_history_tokens.return_value = 512
        mock_cwm.async_should_compress = AsyncMock(return_value=True)
        mock_cwm.config = {
            "models": {
                "default": {"compression_threshold": 512},
            }
        }

        mock_svc = MagicMock()
        mock_svc.compress_kb_results = AsyncMock(return_value=trimmed)

        with (
            patch(_CWM_CLASS, return_value=mock_cwm),
            patch(_COMP_CLASS, return_value=mock_svc),
        ):
            result = await AsyncChatWorkflow._budget_kb_context(kb_results)

        mock_svc.compress_kb_results.assert_called_once()
        call_args = mock_svc.compress_kb_results.call_args
        # First positional arg is kb_results, second kwarg is max_tokens
        assert call_args[0][0] == kb_results
        assert call_args[1]["max_tokens"] == 512

        # Result is rebuilt from trimmed citations via build_grounded_context
        assert "fact A" in result
        assert "[Source 1]" in result

    async def test_oversized_all_trimmed_returns_empty_string(self):
        """compress_kb_results returns empty list → _budget_kb_context returns empty string."""
        from async_chat_workflow import AsyncChatWorkflow

        kb_results = [_make_kb_result("huge fact" * 2000, score=0.9)]

        mock_cwm = MagicMock()
        mock_cwm.estimate_tokens.return_value = 99999
        mock_cwm.get_max_history_tokens.return_value = 512
        mock_cwm.async_should_compress = AsyncMock(return_value=True)
        mock_cwm.config = {"models": {"default": {"compression_threshold": 512}}}

        mock_svc = MagicMock()
        mock_svc.compress_kb_results = AsyncMock(return_value=[])

        with (
            patch(_CWM_CLASS, return_value=mock_cwm),
            patch(_COMP_CLASS, return_value=mock_svc),
        ):
            result = await AsyncChatWorkflow._budget_kb_context(kb_results)

        assert result == ""


# ---------------------------------------------------------------------------
# _generate_llm_response uses _budget_kb_context (not _build_kb_context_string)
# ---------------------------------------------------------------------------


class TestGenerateLlmResponseUsesBudget:
    """_generate_llm_response must call _budget_kb_context for compression parity."""

    async def test_budget_kb_context_invoked_with_kb_results(self):
        """_generate_llm_response calls _budget_kb_context with the provided kb_results."""
        from async_chat_workflow import AsyncChatWorkflow

        workflow = AsyncChatWorkflow()
        kb_results = [_make_kb_result("grounding fact")]
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(return_value=_make_llm_response())

        with patch.object(
            AsyncChatWorkflow, "_budget_kb_context", new=AsyncMock(return_value="[Source 1]\ngrounding fact")
        ) as mock_budget:
            await workflow._generate_llm_response("question", mock_llm, kb_results)

        mock_budget.assert_called_once_with(kb_results)

    async def test_budget_result_reaches_system_prompt(self):
        """Budgeted KB context is prepended to the system prompt sent to the LLM."""
        from async_chat_workflow import AsyncChatWorkflow

        workflow = AsyncChatWorkflow()
        kb_results = [_make_kb_result("budgeted fact")]
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(return_value=_make_llm_response())

        budgeted_context = "[Source 1]\nbudgeted fact"
        with patch.object(AsyncChatWorkflow, "_budget_kb_context", new=AsyncMock(return_value=budgeted_context)):
            await workflow._generate_llm_response("question", mock_llm, kb_results)

        call_messages = mock_llm.chat_completion.call_args[0][0]
        system_msg = next(m for m in call_messages if m.role == "system")
        assert "budgeted fact" in system_msg.content
        assert "[Source 1]" in system_msg.content

    async def test_no_kb_context_when_results_empty(self):
        """(regression) Empty kb_results → _budget_kb_context returns '' → no injection."""
        from async_chat_workflow import AsyncChatWorkflow

        workflow = AsyncChatWorkflow()
        mock_llm = MagicMock()
        mock_llm.chat_completion = AsyncMock(return_value=_make_llm_response())

        await workflow._generate_llm_response("question", mock_llm, [])

        call_messages = mock_llm.chat_completion.call_args[0][0]
        system_msg = next(m for m in call_messages if m.role == "system")
        assert "[Source" not in system_msg.content
        assert "KNOWLEDGE CONTEXT" not in system_msg.content
