# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for Issue #4202 - HookInvoker redesign.

Tests verify:
1. HookInvoker initialization with default configs
2. Invocation mode behavior (collect, transform, until_handled, cancellable)
3. Type validation for transformed values
4. Error handling and logging
5. Config registration and override
"""

from unittest.mock import AsyncMock, patch

import pytest

from middleware.base import Extension, HookContext
from middleware.hook_invoker import (
    HookInvocationConfig,
    HookInvoker,
    InvocationMode,
)
from middleware.hooks import HookPoint
from middleware.manager import ExtensionManager, reset_extension_manager


class TestHookInvocationConfig:
    """Test HookInvocationConfig validation and creation."""

    def test_collect_mode_creation(self):
        """Should create COLLECT config without validation errors."""
        cfg = HookInvocationConfig(mode=InvocationMode.COLLECT)
        cfg.validate()  # Should not raise

    def test_transform_mode_requires_key(self):
        """Should reject TRANSFORM mode without transform_key."""
        cfg = HookInvocationConfig(mode=InvocationMode.TRANSFORM, transform_key=None)
        with pytest.raises(ValueError, match="transform_key"):
            cfg.validate()

    def test_transform_mode_with_key(self):
        """Should create TRANSFORM config with valid key."""
        cfg = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="prompt",
            expected_type=str,
        )
        cfg.validate()  # Should not raise

    def test_cancellable_mode_creation(self):
        """Should create CANCELLABLE config."""
        cfg = HookInvocationConfig(mode=InvocationMode.CANCELLABLE)
        cfg.validate()  # Should not raise

    def test_until_handled_mode_creation(self):
        """Should create UNTIL_HANDLED config."""
        cfg = HookInvocationConfig(mode=InvocationMode.UNTIL_HANDLED)
        cfg.validate()  # Should not raise


class TestHookInvokerInitialization:
    """Test HookInvoker initialization and configuration."""

    def test_initialization(self):
        """Should initialize with ExtensionManager."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)
        assert invoker.manager is manager

    def test_default_configs_registered(self):
        """Should register default configs for all HookPoint members."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)
        for hp in HookPoint:
            assert invoker.get_config(hp) is not None, f"HookPoint.{hp.name} missing explicit config in HookInvoker"

    def test_message_preparation_hooks_configured(self):
        """Should configure message preparation hooks."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)
        cfg = invoker.get_config(HookPoint.AFTER_PROMPT_BUILD)
        assert cfg.mode == InvocationMode.TRANSFORM
        assert cfg.transform_key == "prompt"
        assert cfg.expected_type is str

    def test_llm_interaction_hooks_configured(self):
        """Should configure LLM hooks."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)
        cfg = invoker.get_config(HookPoint.BEFORE_LLM_CALL)
        assert cfg.mode == InvocationMode.CANCELLABLE

    def test_tool_execution_hooks_configured(self):
        """Should configure tool hooks."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)
        cfg = invoker.get_config(HookPoint.BEFORE_TOOL_EXECUTE)
        assert cfg.mode == InvocationMode.CANCELLABLE

    def test_approval_hooks_configured(self):
        """Should configure approval hooks."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)
        cfg = invoker.get_config(HookPoint.APPROVAL_REQUIRED)
        assert cfg.mode == InvocationMode.UNTIL_HANDLED


class TestHookInvokerInvocation:
    """Test HookInvoker invocation methods."""

    @pytest.mark.asyncio
    async def test_invoke_collect_mode(self):
        """Should invoke and collect all results."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        ctx = HookContext(session_id="test", message="hello")

        # Mock the manager's invoke_hook method
        manager.invoke_hook = AsyncMock(return_value=[1, 2, 3])

        results = await invoker.invoke(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)
        assert results == [1, 2, 3]
        manager.invoke_hook.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_transform_mode(self):
        """Should invoke and transform a context value."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        ctx = HookContext(session_id="test", data={"prompt": "original"})

        # Mock the manager's invoke_with_transform method
        manager.invoke_with_transform = AsyncMock(return_value="modified")

        result = await invoker.invoke(HookPoint.AFTER_PROMPT_BUILD, ctx)
        assert result == "modified"
        manager.invoke_with_transform.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_until_handled_mode(self):
        """Should invoke until one handler."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        ctx = HookContext(session_id="test")

        # Mock the manager's invoke_until_handled method
        manager.invoke_until_handled = AsyncMock(return_value="handled")

        result = await invoker.invoke(HookPoint.APPROVAL_REQUIRED, ctx)
        assert result == "handled"
        manager.invoke_until_handled.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_cancellable_mode(self):
        """Should invoke with veto semantics."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        ctx = HookContext(session_id="test")

        # Mock the manager's invoke_cancellable method
        manager.invoke_cancellable = AsyncMock(return_value=True)

        result = await invoker.invoke(HookPoint.BEFORE_LLM_CALL, ctx)
        assert result is True
        manager.invoke_cancellable.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_with_override_config(self):
        """Should use override config over registered."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        ctx = HookContext(session_id="test")

        override_cfg = HookInvocationConfig(mode=InvocationMode.UNTIL_HANDLED)
        manager.invoke_until_handled = AsyncMock(return_value="result")

        result = await invoker.invoke(HookPoint.BEFORE_MESSAGE_PROCESS, ctx, config=override_cfg)
        assert result == "result"
        manager.invoke_until_handled.assert_called_once()

    @pytest.mark.asyncio
    async def test_transform_type_validation(self):
        """Should validate transform result type."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        ctx = HookContext(session_id="test", data={"prompt": "original"})

        # Return wrong type
        manager.invoke_with_transform = AsyncMock(return_value=123)

        # Implementation lives in middleware/ (#7426); patch the canonical module
        # the shimmed HookInvoker actually logs through (#9794).
        with patch("middleware.hook_invoker.logger") as mock_logger:
            result = await invoker.invoke(HookPoint.AFTER_PROMPT_BUILD, ctx)
            assert result == 123
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_register_custom_config(self):
        """Should allow registering custom configs."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        custom_cfg = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="custom",
            expected_type=dict,
        )
        invoker.register_config(HookPoint.SESSION_CREATE, custom_cfg)

        registered = invoker.get_config(HookPoint.SESSION_CREATE)
        assert registered.mode == InvocationMode.TRANSFORM
        assert registered.transform_key == "custom"

    @pytest.mark.asyncio
    async def test_invoke_handles_exceptions(self):
        """Should handle exceptions during invocation."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        ctx = HookContext(session_id="test")
        manager.invoke_hook = AsyncMock(side_effect=ValueError("test error"))

        with pytest.raises(ValueError, match="test error"):
            await invoker.invoke(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)

    def test_list_hooks(self):
        """Should list all configured hooks with modes."""
        manager = ExtensionManager()
        invoker = HookInvoker(manager)

        hooks = invoker.list_hooks()
        hook_names = {h[0] for h in hooks}
        for hp in HookPoint:
            assert hp.name in hook_names, f"HookPoint.{hp.name} missing from list_hooks() output"

        # Verify specific hook names and modes are present
        assert "BEFORE_MESSAGE_PROCESS" in hook_names
        assert "BEFORE_PROMPT_BUILD" in hook_names
        assert "AFTER_PROMPT_BUILD" in hook_names
        assert "BEFORE_LLM_CALL" in hook_names

        hook_modes = {h[1] for h in hooks}
        assert "collect" in hook_modes
        assert "transform" in hook_modes
        assert "cancellable" in hook_modes


class TestHookInvokerIntegration:
    """Integration tests with real Extension instances."""

    @pytest.mark.asyncio
    async def test_invoke_with_real_extensions(self):
        """Should work with real Extension instances."""
        reset_extension_manager()
        manager = ExtensionManager()

        # Create a test extension
        class TestExtension(Extension):
            name = "test"
            priority = 100

            def __init__(self):
                self.called = False

            async def on_hook(self, hook: HookPoint, ctx: HookContext):
                self.called = True
                return None

        ext = TestExtension()
        manager.register(ext)

        invoker = HookInvoker(manager)
        ctx = HookContext(session_id="test")

        await invoker.invoke(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)
        assert ext.called

    @pytest.mark.asyncio
    async def test_transform_with_real_extensions(self):
        """Should transform values through real extensions."""
        reset_extension_manager()
        manager = ExtensionManager()

        class PromptModifier(Extension):
            name = "modifier"
            priority = 100

            async def on_hook(self, hook: HookPoint, ctx: HookContext):
                if hook == HookPoint.AFTER_PROMPT_BUILD:
                    original = ctx.get("prompt")
                    return f"[MODIFIED] {original}"
                return None

        ext = PromptModifier()
        manager.register(ext)

        invoker = HookInvoker(manager)
        ctx = HookContext(session_id="test", data={"prompt": "original prompt"})

        result = await invoker.invoke(HookPoint.AFTER_PROMPT_BUILD, ctx)
        assert result == "[MODIFIED] original prompt"
