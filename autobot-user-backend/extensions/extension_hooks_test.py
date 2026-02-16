# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Issue #658 - Extension Hooks System.

Tests verify:
1. HookPoint enum definitions
2. HookContext functionality
3. Extension base class
4. ExtensionManager registration and invocation
5. Built-in extensions (logging, secret masking)
"""

from typing import Optional

import pytest

from backend.extensions.base import Extension, HookContext
from backend.extensions.builtin import LoggingExtension, SecretMaskingExtension
from backend.extensions.hooks import HookPoint, get_hook_metadata
from backend.extensions.manager import (
    ExtensionManager,
    get_extension_manager,
    reset_extension_manager,
)


class TestHookPoint:
    """Test HookPoint enum definitions."""

    def test_hook_count(self):
        """Should have exactly 22 hook points."""
        assert len(HookPoint) == 22

    def test_message_preparation_hooks(self):
        """Should have message preparation hooks."""
        assert HookPoint.BEFORE_MESSAGE_PROCESS is not None
        assert HookPoint.AFTER_PROMPT_BUILD is not None

    def test_llm_interaction_hooks(self):
        """Should have LLM interaction hooks."""
        assert HookPoint.BEFORE_LLM_CALL is not None
        assert HookPoint.DURING_LLM_STREAMING is not None
        assert HookPoint.AFTER_LLM_RESPONSE is not None

    def test_tool_execution_hooks(self):
        """Should have tool execution hooks."""
        assert HookPoint.BEFORE_TOOL_PARSE is not None
        assert HookPoint.BEFORE_TOOL_EXECUTE is not None
        assert HookPoint.AFTER_TOOL_EXECUTE is not None
        assert HookPoint.TOOL_ERROR is not None

    def test_continuation_loop_hooks(self):
        """Should have continuation loop hooks."""
        assert HookPoint.BEFORE_CONTINUATION is not None
        assert HookPoint.AFTER_CONTINUATION is not None
        assert HookPoint.LOOP_COMPLETE is not None

    def test_error_handling_hooks(self):
        """Should have error handling hooks."""
        assert HookPoint.REPAIRABLE_ERROR is not None
        assert HookPoint.CRITICAL_ERROR is not None

    def test_response_hooks(self):
        """Should have response hooks."""
        assert HookPoint.BEFORE_RESPONSE_SEND is not None
        assert HookPoint.AFTER_RESPONSE_SEND is not None

    def test_session_lifecycle_hooks(self):
        """Should have session lifecycle hooks."""
        assert HookPoint.SESSION_CREATE is not None
        assert HookPoint.SESSION_DESTROY is not None

    def test_knowledge_hooks(self):
        """Should have knowledge integration hooks."""
        assert HookPoint.BEFORE_RAG_QUERY is not None
        assert HookPoint.AFTER_RAG_RESULTS is not None

    def test_approval_hooks(self):
        """Should have approval flow hooks."""
        assert HookPoint.APPROVAL_REQUIRED is not None
        assert HookPoint.APPROVAL_RECEIVED is not None

    def test_hook_metadata_exists(self):
        """Every hook should have metadata."""
        for hook in HookPoint:
            metadata = get_hook_metadata(hook)
            assert "description" in metadata
            assert "can_modify" in metadata
            assert "return_type" in metadata


class TestHookContext:
    """Test HookContext functionality."""

    def test_default_context(self):
        """Context should have default values."""
        ctx = HookContext()
        assert ctx.session_id == ""
        assert ctx.message == ""
        assert ctx.agent_id is None
        assert ctx.data == {}

    def test_context_with_values(self):
        """Context should accept initialization values."""
        ctx = HookContext(
            session_id="sess-123",
            message="Hello",
            agent_id="agent-456",
        )
        assert ctx.session_id == "sess-123"
        assert ctx.message == "Hello"
        assert ctx.agent_id == "agent-456"

    def test_set_and_get(self):
        """set() and get() should work correctly."""
        ctx = HookContext()
        ctx.set("key1", "value1")

        assert ctx.get("key1") == "value1"
        assert ctx.get("missing") is None
        assert ctx.get("missing", "default") == "default"

    def test_merge(self):
        """merge() should update data dictionary."""
        ctx = HookContext()
        ctx.set("existing", "value")
        ctx.merge({"new1": "val1", "new2": "val2"})

        assert ctx.get("existing") == "value"
        assert ctx.get("new1") == "val1"
        assert ctx.get("new2") == "val2"

    def test_has(self):
        """has() should check key existence."""
        ctx = HookContext()
        ctx.set("exists", True)

        assert ctx.has("exists") is True
        assert ctx.has("missing") is False

    def test_remove(self):
        """remove() should remove and return value."""
        ctx = HookContext()
        ctx.set("key", "value")

        removed = ctx.remove("key")
        assert removed == "value"
        assert ctx.has("key") is False
        assert ctx.remove("missing") is None

    def test_to_dict(self):
        """to_dict() should serialize context."""
        ctx = HookContext(
            session_id="sess-123",
            message="Hello",
            agent_id="agent-456",
        )
        ctx.set("custom", "data")

        d = ctx.to_dict()
        assert d["session_id"] == "sess-123"
        assert d["message"] == "Hello"
        assert d["agent_id"] == "agent-456"
        assert d["data"]["custom"] == "data"


class TestExtension:
    """Test Extension base class."""

    def test_default_extension(self):
        """Extension should have default attributes."""
        ext = Extension()
        assert ext.name == "base"
        assert ext.priority == 100
        assert ext.enabled is True

    def test_custom_extension(self):
        """Custom extension should override attributes."""

        class CustomExtension(Extension):
            name = "custom"
            priority = 50

        ext = CustomExtension()
        assert ext.name == "custom"
        assert ext.priority == 50

    @pytest.mark.asyncio
    async def test_hook_dispatch(self):
        """on_hook() should dispatch to specific methods."""

        class TrackingExtension(Extension):
            name = "tracking"

            def __init__(self):
                self.called_hooks = []

            async def on_before_message_process(self, ctx: HookContext):
                self.called_hooks.append("before_message_process")

            async def on_after_llm_response(self, ctx: HookContext):
                self.called_hooks.append("after_llm_response")
                return "modified"

        ext = TrackingExtension()
        ctx = HookContext()

        await ext.on_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)
        result = await ext.on_hook(HookPoint.AFTER_LLM_RESPONSE, ctx)

        assert "before_message_process" in ext.called_hooks
        assert "after_llm_response" in ext.called_hooks
        assert result == "modified"

    @pytest.mark.asyncio
    async def test_disabled_extension(self):
        """Disabled extension should not be called."""

        class CountingExtension(Extension):
            name = "counting"

            def __init__(self):
                self.call_count = 0

            async def on_before_message_process(self, ctx: HookContext):
                self.call_count += 1

        ext = CountingExtension()
        ext.enabled = False
        ctx = HookContext()

        await ext.on_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)

        assert ext.call_count == 0

    @pytest.mark.asyncio
    async def test_extension_error_handling(self):
        """Extension errors should be caught."""

        class FailingExtension(Extension):
            name = "failing"

            async def on_before_message_process(self, ctx: HookContext):
                raise ValueError("Test error")

        ext = FailingExtension()
        ctx = HookContext()

        # Should not raise
        result = await ext.on_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)
        assert result is None


class TestExtensionManager:
    """Test ExtensionManager functionality."""

    def setup_method(self):
        """Reset global manager before each test."""
        reset_extension_manager()

    def test_register_extension(self):
        """register() should add extension."""
        manager = ExtensionManager()
        ext = Extension()
        ext.name = "test"

        result = manager.register(ext)

        assert result is True
        assert "test" in manager.list_extensions()

    def test_register_duplicate(self):
        """register() should reject duplicates."""
        manager = ExtensionManager()
        ext1 = Extension()
        ext1.name = "test"
        ext2 = Extension()
        ext2.name = "test"

        manager.register(ext1)
        result = manager.register(ext2)

        assert result is False
        assert len(manager.extensions) == 1

    def test_unregister_extension(self):
        """unregister() should remove extension."""
        manager = ExtensionManager()
        ext = Extension()
        ext.name = "test"
        manager.register(ext)

        result = manager.unregister("test")

        assert result is True
        assert "test" not in manager.list_extensions()

    def test_get_extension(self):
        """get_extension() should return extension by name."""
        manager = ExtensionManager()
        ext = Extension()
        ext.name = "test"
        manager.register(ext)

        found = manager.get_extension("test")

        assert found is ext
        assert manager.get_extension("missing") is None

    def test_enable_disable_extension(self):
        """enable/disable should toggle extension state."""
        manager = ExtensionManager()
        ext = Extension()
        ext.name = "test"
        manager.register(ext)

        manager.disable_extension("test")
        assert ext.enabled is False

        manager.enable_extension("test")
        assert ext.enabled is True

    def test_priority_ordering(self):
        """Extensions should be ordered by priority."""
        manager = ExtensionManager()

        ext1 = Extension()
        ext1.name = "high"
        ext1.priority = 100

        ext2 = Extension()
        ext2.name = "low"
        ext2.priority = 10

        ext3 = Extension()
        ext3.name = "mid"
        ext3.priority = 50

        manager.register(ext1)
        manager.register(ext2)
        manager.register(ext3)

        names = manager.list_extensions()
        assert names == ["low", "mid", "high"]

    @pytest.mark.asyncio
    async def test_invoke_hook(self):
        """invoke_hook() should call all extensions."""

        class ResultExtension(Extension):
            async def on_before_message_process(self, ctx: HookContext):
                return f"result-{self.name}"

        manager = ExtensionManager()
        ext1 = ResultExtension()
        ext1.name = "ext1"
        ext2 = ResultExtension()
        ext2.name = "ext2"

        manager.register(ext1)
        manager.register(ext2)

        ctx = HookContext()
        results = await manager.invoke_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)

        assert len(results) == 2
        assert "result-ext1" in results
        assert "result-ext2" in results

    @pytest.mark.asyncio
    async def test_invoke_until_handled(self):
        """invoke_until_handled() should stop at first handler."""

        class HandlerExtension(Extension):
            def __init__(self, name: str, priority: int, should_handle: bool):
                self.name = name
                self.priority = priority
                self.enabled = True
                self.should_handle = should_handle

            async def on_approval_required(self, ctx: HookContext) -> Optional[bool]:
                if self.should_handle:
                    return True
                return None

        manager = ExtensionManager()
        ext1 = HandlerExtension("ext1", 10, False)
        ext2 = HandlerExtension("ext2", 20, True)
        ext3 = HandlerExtension("ext3", 30, True)

        manager.register(ext1)
        manager.register(ext2)
        manager.register(ext3)

        ctx = HookContext()
        result = await manager.invoke_until_handled(HookPoint.APPROVAL_REQUIRED, ctx)

        # Should stop at ext2 (first handler)
        assert result is True

    @pytest.mark.asyncio
    async def test_invoke_cancellable(self):
        """invoke_cancellable() should respect cancellation."""

        class CancelExtension(Extension):
            def __init__(self, should_cancel: bool):
                self.should_cancel = should_cancel

            async def on_before_tool_execute(self, ctx: HookContext) -> Optional[bool]:
                if self.should_cancel:
                    return False
                return None

        manager = ExtensionManager()
        ext = CancelExtension(True)
        ext.name = "canceller"

        manager.register(ext)

        ctx = HookContext()
        result = await manager.invoke_cancellable(HookPoint.BEFORE_TOOL_EXECUTE, ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_invoke_with_transform(self):
        """invoke_with_transform() should chain transformations."""

        class TransformExtension(Extension):
            def __init__(self, suffix: str):
                self.suffix = suffix

            async def on_after_prompt_build(self, ctx: HookContext) -> Optional[str]:
                prompt = ctx.get("prompt", "")
                return prompt + self.suffix

        manager = ExtensionManager()
        ext1 = TransformExtension("-A")
        ext1.name = "ext1"
        ext1.priority = 10

        ext2 = TransformExtension("-B")
        ext2.name = "ext2"
        ext2.priority = 20

        manager.register(ext1)
        manager.register(ext2)

        ctx = HookContext()
        ctx.set("prompt", "base")

        result = await manager.invoke_with_transform(
            HookPoint.AFTER_PROMPT_BUILD, ctx, "prompt"
        )

        assert result == "base-A-B"

    def test_load_extensions(self):
        """load_extensions() should register from class list."""
        manager = ExtensionManager()

        count = manager.load_extensions(
            [
                LoggingExtension,
                SecretMaskingExtension,
            ]
        )

        assert count == 2
        assert "logging" in manager.list_extensions()
        assert "secret_masking" in manager.list_extensions()

    def test_get_statistics(self):
        """get_statistics() should return correct info."""
        manager = ExtensionManager()
        ext = Extension()
        ext.name = "test"
        manager.register(ext)
        manager.disable_extension("test")

        stats = manager.get_statistics()

        assert stats["total_extensions"] == 1
        assert stats["enabled_count"] == 0
        assert stats["disabled_count"] == 1

    def test_global_manager(self):
        """get_extension_manager() should return singleton."""
        manager1 = get_extension_manager()
        manager2 = get_extension_manager()

        assert manager1 is manager2


class TestLoggingExtension:
    """Test LoggingExtension built-in."""

    def test_extension_attributes(self):
        """LoggingExtension should have correct attributes."""
        ext = LoggingExtension()
        assert ext.name == "logging"
        assert ext.priority == 1  # Runs first

    @pytest.mark.asyncio
    async def test_logs_message_processing(self):
        """Should log message processing."""
        ext = LoggingExtension()
        ctx = HookContext(session_id="test-session", message="Hello")

        # Should not raise
        await ext.on_before_message_process(ctx)

        assert "test-session" in ext._session_start_times

    @pytest.mark.asyncio
    async def test_logs_tool_execution(self):
        """Should log tool execution."""
        ext = LoggingExtension()
        ctx = HookContext(session_id="test-session")
        ctx.set("tool_name", "test_tool")

        # Should not raise
        result = await ext.on_before_tool_execute(ctx)
        assert result is None  # Doesn't cancel

    @pytest.mark.asyncio
    async def test_tracks_timing(self):
        """Should track session timing."""
        ext = LoggingExtension()
        ctx = HookContext(session_id="test-session", message="Hello")

        await ext.on_before_message_process(ctx)
        assert "test-session" in ext._session_start_times

        await ext.on_loop_complete(ctx)
        assert "test-session" not in ext._session_start_times


class TestSecretMaskingExtension:
    """Test SecretMaskingExtension built-in."""

    def test_extension_attributes(self):
        """SecretMaskingExtension should have correct attributes."""
        ext = SecretMaskingExtension()
        assert ext.name == "secret_masking"
        assert ext.priority == 90  # Runs near end

    def test_default_patterns(self):
        """Should have default patterns loaded."""
        ext = SecretMaskingExtension()
        assert len(ext.patterns) > 0
        assert len(ext.compiled_patterns) > 0

    def test_mask_api_key(self):
        """Should mask API keys."""
        ext = SecretMaskingExtension()
        text = "API_KEY=sk-1234567890abcdefghijklmnopqrstuvwxyz123456"
        masked = ext.mask_secrets(text)

        # Should contain mask characters
        assert "****" in masked
        # Original secret should not be fully visible
        assert text not in masked

    def test_mask_bearer_token(self):
        """Should mask bearer tokens."""
        ext = SecretMaskingExtension()
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        masked = ext.mask_secrets(text)

        assert "****" in masked

    def test_mask_aws_key(self):
        """Should mask AWS access keys."""
        ext = SecretMaskingExtension()
        text = "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"
        masked = ext.mask_secrets(text)

        assert "****" in masked

    def test_mask_password(self):
        """Should mask passwords."""
        ext = SecretMaskingExtension()
        text = "password: mysecretpassword123"
        masked = ext.mask_secrets(text)

        assert "****" in masked

    def test_preserve_safe_text(self):
        """Should not modify safe text."""
        ext = SecretMaskingExtension()
        text = "This is a normal message without secrets."
        masked = ext.mask_secrets(text)

        assert masked == text

    def test_add_custom_pattern(self):
        """add_pattern() should add custom detection."""
        ext = SecretMaskingExtension()
        initial_count = len(ext.patterns)

        ext.add_pattern(r"custom-secret-\w+", "Custom Secret")

        assert len(ext.patterns) == initial_count + 1

    @pytest.mark.asyncio
    async def test_masks_response(self):
        """Should mask secrets in responses."""
        ext = SecretMaskingExtension()
        ctx = HookContext()
        # Use a longer secret that matches the API key pattern (20+ chars)
        secret = "sk-1234567890abcdefghijklmnopqrstuvwxyz123456"
        ctx.set("response", f"Your API key is: api_key={secret}")

        result = await ext.on_before_response_send(ctx)

        assert result is not None
        assert "****" in result
        # Original full secret should not be in result
        assert secret not in result

    def test_get_statistics(self):
        """get_statistics() should return masking stats."""
        ext = SecretMaskingExtension()
        ext.mask_secrets("api_key=sk-1234567890abcdefghijklmnop")

        stats = ext.get_statistics()

        assert stats["pattern_count"] > 0
        assert stats["total_masks_applied"] >= 1


class TestExtensionIntegration:
    """Test extension system integration."""

    def setup_method(self):
        """Reset global manager before each test."""
        reset_extension_manager()

    @pytest.mark.asyncio
    async def test_multiple_extensions_interact(self):
        """Multiple extensions should work together."""
        manager = ExtensionManager()
        manager.load_extensions(
            [
                LoggingExtension,
                SecretMaskingExtension,
            ]
        )

        ctx = HookContext(session_id="test", message="Hello")
        ctx.set("response", "api_key=sk-1234567890abcdefghijklmnop")

        # Invoke hook
        results = await manager.invoke_hook(HookPoint.BEFORE_RESPONSE_SEND, ctx)

        # SecretMaskingExtension should have masked the response
        assert any("****" in str(r) for r in results if r)

    @pytest.mark.asyncio
    async def test_extension_priority_order(self):
        """Extensions should execute in priority order."""
        order = []

        class OrderExtension(Extension):
            def __init__(self, name: str, priority: int):
                self.name = name
                self.priority = priority

            async def on_before_message_process(self, ctx: HookContext):
                order.append(self.name)

        manager = ExtensionManager()
        manager.register(OrderExtension("third", 100))
        manager.register(OrderExtension("first", 10))
        manager.register(OrderExtension("second", 50))

        ctx = HookContext()
        await manager.invoke_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)

        assert order == ["first", "second", "third"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
