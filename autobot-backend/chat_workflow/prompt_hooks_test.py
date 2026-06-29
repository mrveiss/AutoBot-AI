# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for Issue #3405 — ON_SYSTEM_PROMPT_READY and ON_FULL_PROMPT_READY
plugin hooks in the chat pipeline.

Tests verify:
1. New HookPoint enum members exist
2. ON_SYSTEM_PROMPT_READY fires with correct args and return value replaces prompt
3. ON_FULL_PROMPT_READY fires with correct args and return value replaces prompt
4. No-op when no extensions are registered for a hook
5. Extension errors do not crash the pipeline
"""

import pytest

from chat_workflow.llm_handler import _emit_full_prompt_ready, _emit_system_prompt_ready
from middleware.base import Extension, HookContext
from middleware.hooks import HookPoint
from middleware.manager import reset_extension_manager


class _SystemPromptWatcher(Extension):
    """Extension that records args and returns a modified system prompt."""

    name = "test_system_prompt_watcher"

    def __init__(self, return_value: str | None = None) -> None:
        self._return_value = return_value
        self.captured_system_prompt: str | None = None

    async def on_system_prompt_ready(self, ctx: HookContext) -> str | None:
        self.captured_system_prompt = ctx.get("system_prompt")
        return self._return_value


class _FullPromptWatcher(Extension):
    """Extension that records args and returns a modified full prompt."""

    name = "test_full_prompt_watcher"

    def __init__(self, return_value: str | None = None) -> None:
        self._return_value = return_value
        self.captured_prompt: str | None = None
        self.captured_llm_params: dict | None = None
        self.captured_context: dict | None = None

    async def on_full_prompt_ready(self, ctx: HookContext) -> str | None:
        self.captured_prompt = ctx.get("prompt")
        self.captured_llm_params = ctx.get("llm_params")
        self.captured_context = ctx.get("context")
        return self._return_value


class _ErrorExtension(Extension):
    """Extension that always raises an exception."""

    name = "test_error_extension"

    async def on_full_prompt_ready(self, ctx: HookContext) -> str | None:
        raise RuntimeError("simulated extension failure")


class _FakeSession:
    session_id = "sess-test-001"
    metadata: dict = {}


@pytest.fixture(autouse=True)
def reset_manager():
    """Ensure global ExtensionManager is reset between tests."""
    reset_extension_manager()
    yield
    reset_extension_manager()


class TestNewHookPoints:
    """Verify the new HookPoint members are present."""

    def test_on_system_prompt_ready_exists(self):
        assert HookPoint.SYSTEM_PROMPT_READY is not None

    def test_on_full_prompt_ready_exists(self):
        assert HookPoint.FULL_PROMPT_READY is not None

    def test_total_hook_count_increased(self):
        # Original 22 hooks + 3 new ones = 25
        assert len(HookPoint) == 25


class TestEmitSystemPromptReady:
    """Tests for _emit_system_prompt_ready helper."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original prompt unchanged when no extension is registered."""
        original = "You are AutoBot."
        result = await _emit_system_prompt_ready(original, _FakeSession())
        assert result == original

    @pytest.mark.asyncio
    async def test_extension_receives_correct_args(self):
        """Extension receives system_prompt and session via HookContext."""
        watcher = _SystemPromptWatcher(return_value=None)
        from middleware.manager import get_extension_manager

        get_extension_manager().register(watcher)

        original = "You are AutoBot."
        session = _FakeSession()
        await _emit_system_prompt_ready(original, session)

        assert watcher.captured_system_prompt == original

    @pytest.mark.asyncio
    async def test_return_value_replaces_prompt(self):
        """A non-None str returned by extension replaces the system prompt."""
        modified = "You are AutoBot [modified by extension]."
        watcher = _SystemPromptWatcher(return_value=modified)
        from middleware.manager import get_extension_manager

        get_extension_manager().register(watcher)

        result = await _emit_system_prompt_ready("You are AutoBot.", _FakeSession())
        assert result == modified

    @pytest.mark.asyncio
    async def test_none_return_keeps_original(self):
        """Returning None from extension keeps the original prompt."""
        watcher = _SystemPromptWatcher(return_value=None)
        from middleware.manager import get_extension_manager

        get_extension_manager().register(watcher)

        original = "You are AutoBot."
        result = await _emit_system_prompt_ready(original, _FakeSession())
        assert result == original


class TestEmitFullPromptReady:
    """Tests for _emit_full_prompt_ready helper."""

    @pytest.mark.asyncio
    async def test_noop_when_no_extension_registered(self):
        """Returns original prompt unchanged when no extension is registered."""
        original = "System prompt\n\nUser: hello\n\nAssistant:"
        result = await _emit_full_prompt_ready(original, {}, {})
        assert result == original

    @pytest.mark.asyncio
    async def test_extension_receives_correct_args(self):
        """Extension receives prompt, llm_params and context via HookContext."""
        watcher = _FullPromptWatcher(return_value=None)
        from middleware.manager import get_extension_manager

        get_extension_manager().register(watcher)

        original = "System prompt\n\nUser: hello\n\nAssistant:"
        llm_params = {"model": "llama3", "endpoint": "http://localhost:11434/api/generate"}  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
        context = {"session_id": "sess-abc", "message": "hello"}

        await _emit_full_prompt_ready(original, llm_params, context)

        assert watcher.captured_prompt == original
        assert watcher.captured_llm_params == llm_params
        assert watcher.captured_context == context

    @pytest.mark.asyncio
    async def test_return_value_replaces_prompt(self):
        """A non-None str returned by extension replaces the full prompt."""
        modified = "System prompt\n\nUser: hello\n\nAssistant:\n\n[hint: be concise]"
        watcher = _FullPromptWatcher(return_value=modified)
        from middleware.manager import get_extension_manager

        get_extension_manager().register(watcher)

        result = await _emit_full_prompt_ready("System prompt\n\nUser: hello\n\nAssistant:", {}, {})
        assert result == modified

    @pytest.mark.asyncio
    async def test_extension_error_does_not_crash_pipeline(self):
        """An exception inside an extension is swallowed; original prompt is returned."""
        from middleware.manager import get_extension_manager

        get_extension_manager().register(_ErrorExtension())

        original = "System prompt\n\nUser: hello\n\nAssistant:"
        result = await _emit_full_prompt_ready(original, {}, {})
        assert result == original
