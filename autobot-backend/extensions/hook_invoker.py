# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Centralized hook invocation strategy for extensibility.

Issue #4202: Redesigns hook invocation to eliminate boilerplate and
improve extensibility through a unified invocation strategy.

This module provides:
- HookInvoker: Central coordinator for all hook invocations
- Hook configuration with declarative patterns (transform, cancel, collect)
- Consistent error handling and logging across all hook points
"""

from enum import Enum
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from extensions.base import HookContext
from extensions.hooks import HookPoint
from extensions.manager import ExtensionManager

logger = get_logger(__name__)


class InvocationMode(Enum):
    """
    Strategy for how a hook should be invoked.

    COLLECT: Invoke all extensions, collect all non-None results (default)
    TRANSFORM: Invoke all extensions with transform semantics on a specific key
    UNTIL_HANDLED: Stop at first truthy result (one-winner pattern)
    CANCELLABLE: Stop if any extension returns False (veto pattern)
    """

    COLLECT = "collect"
    TRANSFORM = "transform"
    UNTIL_HANDLED = "until_handled"
    CANCELLABLE = "cancellable"


class HookInvocationConfig:
    """Configuration for how a specific hook should be invoked."""

    def __init__(
        self,
        mode: InvocationMode = InvocationMode.COLLECT,
        transform_key: str | None = None,
        expected_type: type | None = None,
    ):
        """
        Initialize hook invocation configuration.

        Args:
            mode: How the hook should be invoked
            transform_key: For TRANSFORM mode, which context key to transform
            expected_type: For TRANSFORM mode, validate result type (e.g., str)
        """
        self.mode = mode
        self.transform_key = transform_key
        self.expected_type = expected_type

    def validate(self) -> None:
        """Validate configuration consistency."""
        if self.mode == InvocationMode.TRANSFORM:
            if not self.transform_key:
                raise ValueError("TRANSFORM mode requires transform_key")


class HookInvoker:
    """
    Centralized hook invocation coordinator.

    Issue #4202: Eliminates repetitive _emit_* wrapper functions by
    providing a unified invocation interface with configurable strategies.

    Usage:
        invoker = HookInvoker(extension_manager)

        # Collect all results
        results = await invoker.invoke(
            HookPoint.BEFORE_MESSAGE_PROCESS,
            ctx
        )

        # Transform a specific context value
        modified_prompt = await invoker.invoke(
            HookPoint.AFTER_PROMPT_BUILD,
            ctx,
            config=HookInvocationConfig(
                mode=InvocationMode.TRANSFORM,
                transform_key="prompt",
                expected_type=str
            )
        )

        # Stop at first handler (veto pattern)
        should_proceed = await invoker.invoke(
            HookPoint.BEFORE_LLM_CALL,
            ctx,
            config=HookInvocationConfig(mode=InvocationMode.CANCELLABLE)
        )
    """

    def __init__(self, manager: ExtensionManager):
        """
        Initialize HookInvoker.

        Args:
            manager: ExtensionManager instance for invoking extensions
        """
        self.manager = manager
        self._configs: Dict[HookPoint, HookInvocationConfig] = {}
        self._register_default_configs()

    def _register_default_configs(self) -> None:
        """Register default invocation configurations for all hooks."""
        # Message preparation hooks
        self._configs[HookPoint.BEFORE_MESSAGE_PROCESS] = HookInvocationConfig(mode=InvocationMode.COLLECT)
        self._configs[HookPoint.BEFORE_PROMPT_BUILD] = HookInvocationConfig(mode=InvocationMode.COLLECT)
        self._configs[HookPoint.AFTER_PROMPT_BUILD] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="prompt",
            expected_type=str,
        )

        # LLM interaction hooks
        self._configs[HookPoint.BEFORE_LLM_CALL] = HookInvocationConfig(mode=InvocationMode.CANCELLABLE)
        self._configs[HookPoint.DURING_LLM_STREAMING] = HookInvocationConfig(mode=InvocationMode.COLLECT)
        self._configs[HookPoint.AFTER_LLM_RESPONSE] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="response",
            expected_type=str,
        )

        # Tool execution hooks
        self._configs[HookPoint.BEFORE_TOOL_PARSE] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="llm_response",
            expected_type=str,
        )
        self._configs[HookPoint.BEFORE_TOOL_EXECUTE] = HookInvocationConfig(mode=InvocationMode.CANCELLABLE)
        self._configs[HookPoint.AFTER_TOOL_EXECUTE] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="tool_result",
        )
        self._configs[HookPoint.TOOL_ERROR] = HookInvocationConfig(mode=InvocationMode.COLLECT)

        # Continuation loop hooks
        self._configs[HookPoint.BEFORE_CONTINUATION] = HookInvocationConfig(mode=InvocationMode.CANCELLABLE)
        self._configs[HookPoint.AFTER_CONTINUATION] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="response",
            expected_type=str,
        )
        self._configs[HookPoint.LOOP_COMPLETE] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="final_response",
            expected_type=str,
        )

        # Error handling hooks
        self._configs[HookPoint.REPAIRABLE_ERROR] = HookInvocationConfig(mode=InvocationMode.COLLECT)
        self._configs[HookPoint.CRITICAL_ERROR] = HookInvocationConfig(mode=InvocationMode.COLLECT)

        # Response hooks
        self._configs[HookPoint.BEFORE_RESPONSE_SEND] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="response",
        )
        self._configs[HookPoint.AFTER_RESPONSE_SEND] = HookInvocationConfig(mode=InvocationMode.COLLECT)

        # Session lifecycle hooks
        self._configs[HookPoint.SESSION_CREATE] = HookInvocationConfig(mode=InvocationMode.COLLECT)
        self._configs[HookPoint.SESSION_DESTROY] = HookInvocationConfig(mode=InvocationMode.COLLECT)

        # Knowledge integration hooks
        self._configs[HookPoint.BEFORE_RAG_QUERY] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="query",
            expected_type=str,
        )
        self._configs[HookPoint.AFTER_RAG_RESULTS] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="results",
        )

        # Approval flow hooks
        self._configs[HookPoint.APPROVAL_REQUIRED] = HookInvocationConfig(mode=InvocationMode.UNTIL_HANDLED)
        self._configs[HookPoint.APPROVAL_RECEIVED] = HookInvocationConfig(mode=InvocationMode.COLLECT)

        # Prompt pipeline hooks (Issue #3405)
        self._configs[HookPoint.SYSTEM_PROMPT_READY] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="system_prompt",
            expected_type=str,
        )
        self._configs[HookPoint.FULL_PROMPT_READY] = HookInvocationConfig(
            mode=InvocationMode.TRANSFORM,
            transform_key="prompt",
            expected_type=str,
        )

    def register_config(self, hook: HookPoint, config: HookInvocationConfig) -> None:
        """
        Register or override a hook's invocation configuration.

        Args:
            hook: The hook point to configure
            config: Configuration specifying how to invoke it
        """
        config.validate()
        self._configs[hook] = config
        logger.debug(
            "[Issue #4202] Registered %s config for %s",
            config.mode.value,
            hook.name,
        )

    async def invoke(
        self,
        hook: HookPoint,
        context: HookContext,
        config: HookInvocationConfig | None = None,
    ) -> Any:
        """
        Invoke a hook using its registered strategy.

        Args:
            hook: The hook point to invoke
            context: Hook context with data to pass to extensions
            config: Optional override configuration (uses registered if None)

        Returns:
            Result based on invocation mode:
            - COLLECT: List of non-None results
            - TRANSFORM: Transformed value (or original if no transform)
            - UNTIL_HANDLED: First truthy result or None
            - CANCELLABLE: True if should proceed, False if vetoed
        """
        cfg = config or self._configs.get(hook)
        if not cfg:
            # Fallback to default COLLECT strategy
            cfg = HookInvocationConfig(mode=InvocationMode.COLLECT)

        try:
            if cfg.mode == InvocationMode.COLLECT:
                return await self._invoke_collect(hook, context)
            elif cfg.mode == InvocationMode.TRANSFORM:
                return await self._invoke_transform(hook, context, cfg.transform_key, cfg.expected_type)
            elif cfg.mode == InvocationMode.UNTIL_HANDLED:
                return await self._invoke_until_handled(hook, context)
            elif cfg.mode == InvocationMode.CANCELLABLE:
                return await self._invoke_cancellable(hook, context)
            else:
                # Default to COLLECT
                return await self._invoke_collect(hook, context)
        except Exception as e:
            logger.error(
                "[Issue #4202] Failed to invoke %s: %s",
                hook.name,
                str(e),
                exc_info=True,
            )
            raise

    async def _invoke_collect(self, hook: HookPoint, context: HookContext) -> List[Any]:
        """
        Collect all non-None results from extensions.

        Args:
            hook: The hook point to invoke
            context: Hook context

        Returns:
            List of non-None results
        """
        return await self.manager.invoke_hook(hook, context)

    async def _invoke_transform(
        self,
        hook: HookPoint,
        context: HookContext,
        key: str,
        expected_type: type | None,
    ) -> Any:
        """
        Transform a context value through all extensions.

        Args:
            hook: The hook point to invoke
            context: Hook context
            key: Context key to transform
            expected_type: Expected type of result (for validation)

        Returns:
            Transformed value or original if unchanged
        """
        result = await self.manager.invoke_with_transform(hook, context, key)

        # Validate type if expected
        if expected_type and result is not None:
            if not isinstance(result, expected_type):
                logger.warning(
                    "[Issue #4202] %s returned %s, expected %s",
                    hook.name,
                    type(result).__name__,
                    expected_type.__name__,
                )
        return result

    async def _invoke_until_handled(self, hook: HookPoint, context: HookContext) -> Any | None:
        """
        Invoke until one extension handles (returns truthy value).

        Args:
            hook: The hook point to invoke
            context: Hook context

        Returns:
            First truthy result or None
        """
        return await self.manager.invoke_until_handled(hook, context)

    async def _invoke_cancellable(self, hook: HookPoint, context: HookContext) -> bool:
        """
        Invoke with veto semantics - False cancels operation.

        Args:
            hook: The hook point to invoke
            context: Hook context

        Returns:
            True if should proceed, False if vetoed
        """
        return await self.manager.invoke_cancellable(hook, context)

    def get_config(self, hook: HookPoint) -> HookInvocationConfig | None:
        """
        Get the registered configuration for a hook.

        Args:
            hook: The hook point

        Returns:
            Configuration or None if using default
        """
        return self._configs.get(hook)

    def list_hooks(self) -> List[tuple]:
        """
        List all configured hooks with their modes.

        Returns:
            List of (hook_name, mode) tuples
        """
        return [(hook.name, cfg.mode.value) for hook, cfg in self._configs.items()]
