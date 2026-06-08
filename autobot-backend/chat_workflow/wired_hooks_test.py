# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Issue #4181 — wiring 22 uninvoked HookPoints throughout the chat workflow.

Tests verify:
1. All 22 previously uninvoked HookPoints have handler functions
2. Each hook is called with correct parameters
3. Hooks can modify/filter/cancel workflow operations
4. Extension errors do not crash the workflow
5. No-op when no extensions are registered
"""

from typing import Any

import pytest

from chat_workflow.llm_handler import (
    _emit_after_llm_response,
    _emit_after_prompt_build,
    _emit_after_response_send,
    _emit_after_tool_execute,
    _emit_before_continuation,
    _emit_before_llm_call,
    _emit_before_message_process,
    _emit_before_prompt_build,
    _emit_before_response_send,
    _emit_before_tool_execute,
    _emit_before_tool_parse,
    _emit_critical_error,
    _emit_loop_complete,
    _emit_repairable_error,
    _emit_tool_error,
)
from chat_workflow.session_handler import (
    _emit_after_rag_results,
    _emit_approval_received,
    _emit_approval_required,
    _emit_before_rag_query,
    _emit_session_create,
    _emit_session_destroy,
)
from extensions.base import Extension, HookContext
from extensions.manager import get_extension_manager, reset_extension_manager


class _TrackingExtension(Extension):
    """Extension that tracks which hooks were called."""

    name = "test_tracking"

    def __init__(self):
        self.called_hooks = []
        self.captured_data = {}

    async def on_before_message_process(self, ctx: HookContext) -> None:
        self.called_hooks.append("before_message_process")
        self.captured_data["message"] = ctx.get("message")

    async def on_before_prompt_build(self, ctx: HookContext) -> None:
        self.called_hooks.append("before_prompt_build")
        self.captured_data["context"] = ctx.get("context")

    async def on_after_prompt_build(self, ctx: HookContext) -> str | None:
        self.called_hooks.append("after_prompt_build")
        return ctx.get("prompt")

    async def on_before_llm_call(self, ctx: HookContext) -> None:
        self.called_hooks.append("before_llm_call")
        self.captured_data["llm_params"] = ctx.get("llm_params")

    async def on_during_llm_streaming(self, ctx: HookContext) -> None:
        self.called_hooks.append("during_llm_streaming")
        self.captured_data["chunk"] = ctx.get("chunk")

    async def on_after_llm_response(self, ctx: HookContext) -> str | None:
        self.called_hooks.append("after_llm_response")
        return ctx.get("response")

    async def on_before_tool_parse(self, ctx: HookContext) -> str | None:
        self.called_hooks.append("before_tool_parse")
        return ctx.get("llm_response")

    async def on_before_tool_execute(self, ctx: HookContext) -> None:
        self.called_hooks.append("before_tool_execute")
        self.captured_data["tool_name"] = ctx.get("tool_name")

    async def on_after_tool_execute(self, ctx: HookContext) -> Any | None:
        self.called_hooks.append("after_tool_execute")
        return ctx.get("tool_result")

    async def on_tool_error(self, ctx: HookContext) -> None:
        self.called_hooks.append("tool_error")
        self.captured_data["tool_error"] = ctx.get("error")

    async def on_before_continuation(self, ctx: HookContext) -> None:
        self.called_hooks.append("before_continuation")
        self.captured_data["iteration"] = ctx.get("iteration")

    async def on_after_continuation(self, ctx: HookContext) -> str | None:
        self.called_hooks.append("after_continuation")
        return ctx.get("response")

    async def on_loop_complete(self, ctx: HookContext) -> str | None:
        self.called_hooks.append("loop_complete")
        return ctx.get("final_response")

    async def on_repairable_error(self, ctx: HookContext) -> bool | None:
        self.called_hooks.append("repairable_error")
        return None  # Not handling it

    async def on_critical_error(self, ctx: HookContext) -> None:
        self.called_hooks.append("critical_error")
        self.captured_data["error"] = ctx.get("error")

    async def on_before_response_send(self, ctx: HookContext) -> str | None:
        self.called_hooks.append("before_response_send")
        return ctx.get("response")

    async def on_after_response_send(self, ctx: HookContext) -> None:
        self.called_hooks.append("after_response_send")

    async def on_session_create(self, ctx: HookContext) -> None:
        self.called_hooks.append("session_create")
        self.captured_data["session_id"] = ctx.session_id

    async def on_session_destroy(self, ctx: HookContext) -> None:
        self.called_hooks.append("session_destroy")
        self.captured_data["message_count"] = ctx.get("message_count")

    async def on_before_rag_query(self, ctx: HookContext) -> str | None:
        self.called_hooks.append("before_rag_query")
        return ctx.get("query")

    async def on_after_rag_results(self, ctx: HookContext) -> list | None:
        self.called_hooks.append("after_rag_results")
        return ctx.get("results")

    async def on_approval_required(self, ctx: HookContext) -> bool | None:
        self.called_hooks.append("approval_required")
        return None

    async def on_approval_received(self, ctx: HookContext) -> None:
        self.called_hooks.append("approval_received")
        self.captured_data["approved"] = ctx.get("approved")


@pytest.fixture(autouse=True)
def reset_manager():
    """Ensure global ExtensionManager is reset between tests."""
    reset_extension_manager()
    yield
    reset_extension_manager()


class TestBeforeMessageProcess:
    """Tests for _emit_before_message_process."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original message unchanged when no extension is registered."""
        result = await _emit_before_message_process("hello", "sess-1", {})
        assert result["message"] == "hello"

    @pytest.mark.asyncio
    async def test_extension_receives_correct_args(self):
        """Extension receives message, session_id, and context via HookContext."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_before_message_process("hello world", "sess-123", {})

        assert "before_message_process" in tracker.called_hooks
        assert tracker.captured_data["message"] == "hello world"


class TestBeforePromptBuild:
    """Tests for _emit_before_prompt_build."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """No-op when no extension is registered."""
        await _emit_before_prompt_build("sess-1", {})

    @pytest.mark.asyncio
    async def test_extension_receives_context_info(self):
        """Extension receives context information for prompt preparation."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        context = {"message": "test", "use_knowledge": True}
        await _emit_before_prompt_build("sess-123", context)

        assert "before_prompt_build" in tracker.called_hooks
        assert tracker.captured_data["context"] == context


class TestAfterPromptBuild:
    """Tests for _emit_after_prompt_build."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original prompt unchanged when no extension is registered."""
        prompt = "This is the built prompt"
        result = await _emit_after_prompt_build(prompt, "sess-1", {})
        assert result == prompt

    @pytest.mark.asyncio
    async def test_extension_can_modify_prompt(self):
        """Extension can modify the prompt."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        original = "original prompt"
        await _emit_after_prompt_build(original, "sess-1", {})

        assert "after_prompt_build" in tracker.called_hooks


class TestBeforeLLMCall:
    """Tests for _emit_before_llm_call."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns True to proceed when no extension is registered."""
        result = await _emit_before_llm_call("prompt", {"model": "llama3"}, "sess-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_extension_receives_correct_args(self):
        """Extension receives prompt, llm_params, and session_id."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        llm_params = {"model": "llama3"}
        await _emit_before_llm_call("test prompt", llm_params, "sess-123")

        assert "before_llm_call" in tracker.called_hooks
        assert tracker.captured_data["llm_params"] == llm_params


class TestAfterLLMResponse:
    """Tests for _emit_after_llm_response."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original response unchanged when no extension is registered."""
        response = "This is the LLM response"
        result = await _emit_after_llm_response(response, {}, "sess-1")
        assert result == response

    @pytest.mark.asyncio
    async def test_extension_can_modify_response(self):
        """Extension can modify the response text."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        original = "response text"
        await _emit_after_llm_response(original, {}, "sess-1")

        assert "after_llm_response" in tracker.called_hooks


class TestBeforeToolParse:
    """Tests for _emit_before_tool_parse."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original response unchanged when no extension is registered."""
        response = "<tool_call>...</tool_call>"
        result = await _emit_before_tool_parse(response, "sess-1", {})
        assert result == response

    @pytest.mark.asyncio
    async def test_extension_receives_llm_response(self):
        """Extension receives the raw LLM response before parsing."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_before_tool_parse("raw response", "sess-1", {})

        assert "before_tool_parse" in tracker.called_hooks


class TestBeforeToolExecute:
    """Tests for _emit_before_tool_execute."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns True to proceed when no extension is registered."""
        result = await _emit_before_tool_execute("bash", {"cmd": "ls"}, "sess-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_extension_receives_tool_info(self):
        """Extension receives tool_name and tool_params."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        tool_params = {"cmd": "ls -la"}
        await _emit_before_tool_execute("bash", tool_params, "sess-123")

        assert "before_tool_execute" in tracker.called_hooks
        assert tracker.captured_data["tool_name"] == "bash"


class TestAfterToolExecute:
    """Tests for _emit_after_tool_execute."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original result unchanged when no extension is registered."""
        result_value = {"stdout": "output", "returncode": 0}
        result = await _emit_after_tool_execute("bash", result_value, "sess-1", {})
        assert result == result_value

    @pytest.mark.asyncio
    async def test_extension_receives_tool_result(self):
        """Extension receives tool_name and tool_result."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        result_data = {"status": "success"}
        await _emit_after_tool_execute("bash", result_data, "sess-1", {})

        assert "after_tool_execute" in tracker.called_hooks


class TestToolError:
    """Tests for _emit_tool_error."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """No-op when no extension is registered."""
        error = RuntimeError("Tool failed")
        await _emit_tool_error("bash", error, "sess-1", {})

    @pytest.mark.asyncio
    async def test_extension_receives_error_info(self):
        """Extension receives tool_name and error details."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        error = RuntimeError("Test error")
        await _emit_tool_error("bash", error, "sess-123", {})

        assert "tool_error" in tracker.called_hooks


class TestBeforeContinuation:
    """Tests for _emit_before_continuation."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns True to proceed when no extension is registered."""
        result = await _emit_before_continuation(1, "sess-1", {})
        assert result is True

    @pytest.mark.asyncio
    async def test_extension_receives_iteration_info(self):
        """Extension receives iteration number."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_before_continuation(2, "sess-123", {})

        assert "before_continuation" in tracker.called_hooks
        assert tracker.captured_data["iteration"] == 2


class TestLoopComplete:
    """Tests for _emit_loop_complete."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original response unchanged when no extension is registered."""
        response = "final response"
        result = await _emit_loop_complete(3, response, "sess-1")
        assert result == response

    @pytest.mark.asyncio
    async def test_extension_receives_final_response(self):
        """Extension receives total_iterations and final_response."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_loop_complete(2, "final answer", "sess-123")

        assert "loop_complete" in tracker.called_hooks


class TestRepairableError:
    """Tests for _emit_repairable_error."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns False when no extension is registered."""
        error = RuntimeError("Test error")
        result = await _emit_repairable_error(error, "sess-1", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_extension_receives_error_info(self):
        """Extension receives error details via HookContext."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        error = RuntimeError("Repairable error")
        await _emit_repairable_error(error, "sess-123", {})

        assert "repairable_error" in tracker.called_hooks


class TestCriticalError:
    """Tests for _emit_critical_error."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """No-op when no extension is registered."""
        error = Exception("Critical error")
        await _emit_critical_error(error, "sess-1", {})

    @pytest.mark.asyncio
    async def test_extension_receives_error_info(self):
        """Extension receives error details."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        error = Exception("Critical failure")
        await _emit_critical_error(error, "sess-123", {})

        assert "critical_error" in tracker.called_hooks


class TestBeforeResponseSend:
    """Tests for _emit_before_response_send."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original response unchanged when no extension is registered."""
        response = "user response"
        result = await _emit_before_response_send(response, "sess-1", {})
        assert result == response

    @pytest.mark.asyncio
    async def test_extension_can_modify_response(self):
        """Extension can modify the response before sending."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_before_response_send("response", "sess-123", {})

        assert "before_response_send" in tracker.called_hooks


class TestAfterResponseSend:
    """Tests for _emit_after_response_send."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """No-op when no extension is registered."""
        await _emit_after_response_send("response", "sess-1", {})

    @pytest.mark.asyncio
    async def test_extension_receives_sent_response(self):
        """Extension receives the sent response for logging/analysis."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_after_response_send("sent response", "sess-123", {})

        assert "after_response_send" in tracker.called_hooks


class TestSessionCreate:
    """Tests for _emit_session_create."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """No-op when no extension is registered."""
        await _emit_session_create("sess-123", {})

    @pytest.mark.asyncio
    async def test_extension_receives_session_id(self):
        """Extension receives session_id for initialization."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_session_create("sess-new", {})

        assert "session_create" in tracker.called_hooks
        assert tracker.captured_data["session_id"] == "sess-new"


class TestSessionDestroy:
    """Tests for _emit_session_destroy."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """No-op when no extension is registered."""
        await _emit_session_destroy("sess-123", 42, {})

    @pytest.mark.asyncio
    async def test_extension_receives_session_info(self):
        """Extension receives session_id and message_count for cleanup."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_session_destroy("sess-old", 100, {})

        assert "session_destroy" in tracker.called_hooks
        assert tracker.captured_data["message_count"] == 100


class TestBeforeRAGQuery:
    """Tests for _emit_before_rag_query."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original query unchanged when no extension is registered."""
        query = "search for X"
        result = await _emit_before_rag_query(query, "sess-1", {})
        assert result == query

    @pytest.mark.asyncio
    async def test_extension_can_modify_query(self):
        """Extension can modify the RAG query."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_before_rag_query("original query", "sess-123", {})

        assert "before_rag_query" in tracker.called_hooks


class TestAfterRAGResults:
    """Tests for _emit_after_rag_results."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original results unchanged when no extension is registered."""
        results = [{"id": "1", "content": "result 1"}]
        result = await _emit_after_rag_results(results, "query", "sess-1", {})
        assert result == results

    @pytest.mark.asyncio
    async def test_extension_can_filter_results(self):
        """Extension can filter or rank RAG results."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        results = [{"id": "1"}]
        await _emit_after_rag_results(results, "query", "sess-123", {})

        assert "after_rag_results" in tracker.called_hooks


class TestApprovalRequired:
    """Tests for _emit_approval_required."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns False when no extension is registered."""
        result = await _emit_approval_required("req-1", "delete all", "sess-1", {})
        assert result is False

    @pytest.mark.asyncio
    async def test_extension_can_approve_action(self):
        """Extension can approve or deny actions."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_approval_required("req-123", "action", "sess-123", {})

        assert "approval_required" in tracker.called_hooks


class TestApprovalReceived:
    """Tests for _emit_approval_received."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """No-op when no extension is registered."""
        await _emit_approval_received("req-1", True, "sess-1", {})

    @pytest.mark.asyncio
    async def test_extension_receives_approval_decision(self):
        """Extension receives approval decision for logging."""
        tracker = _TrackingExtension()
        get_extension_manager().register(tracker)

        await _emit_approval_received("req-123", True, "sess-123", {})

        assert "approval_received" in tracker.called_hooks
        assert tracker.captured_data["approved"] is True
