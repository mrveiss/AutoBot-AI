# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Extension Manager for registration and invocation.

Issue #658: Manages the lifecycle of extensions and coordinates
hook invocations across all registered extensions.
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Type

from extensions.base import Extension, HookContext
from extensions.hooks import HookPoint

logger = logging.getLogger(__name__)


class ExtensionManager:
    """
    Manages extension registration and hook invocation.

    Issue #658: Central coordinator for the extension system. Extensions
    are sorted by priority and invoked in order at each hook point.

    Usage:
        manager = ExtensionManager()

        # Register extensions
        manager.register(LoggingExtension())
        manager.register(SecretMaskingExtension())

        # Or load from a list
        manager.load_extensions([LoggingExtension, SecretMaskingExtension])

        # Invoke hooks
        ctx = HookContext(session_id="sess-123", message="Hello")
        results = await manager.invoke_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)

        # Or invoke until one extension handles
        result = await manager.invoke_until_handled(
            HookPoint.ON_APPROVAL_REQUIRED,
            ctx
        )
    """

    def __init__(self):
        """Initialize extension manager."""
        self.extensions: List[Extension] = []
        self._extension_map: Dict[str, Extension] = {}

        logger.info("[Issue #658] ExtensionManager initialized")

    def register(self, extension: Extension) -> bool:
        """
        Register an extension.

        Extensions are sorted by priority (lower = runs first).

        Args:
            extension: Extension instance to register

        Returns:
            True if registered, False if duplicate name
        """
        if extension.name in self._extension_map:
            logger.warning(
                "[Issue #658] Extension '%s' already registered, skipping",
                extension.name,
            )
            return False

        self.extensions.append(extension)
        self._extension_map[extension.name] = extension

        # Sort by priority
        self.extensions.sort(key=lambda e: e.priority)

        logger.info(
            "[Issue #658] Registered extension '%s' (priority=%d)",
            extension.name,
            extension.priority,
        )
        return True

    def unregister(self, name: str) -> bool:
        """
        Unregister an extension by name.

        Args:
            name: Extension name to unregister

        Returns:
            True if unregistered, False if not found
        """
        if name not in self._extension_map:
            return False

        extension = self._extension_map.pop(name)
        self.extensions.remove(extension)

        logger.info("[Issue #658] Unregistered extension '%s'", name)
        return True

    def get_extension(self, name: str) -> Optional[Extension]:
        """
        Get an extension by name.

        Args:
            name: Extension name

        Returns:
            Extension instance or None
        """
        return self._extension_map.get(name)

    def enable_extension(self, name: str) -> bool:
        """
        Enable an extension by name.

        Args:
            name: Extension name

        Returns:
            True if enabled, False if not found
        """
        extension = self._extension_map.get(name)
        if extension:
            extension.enabled = True
            logger.info("[Issue #658] Enabled extension '%s'", name)
            return True
        return False

    def disable_extension(self, name: str) -> bool:
        """
        Disable an extension by name.

        Args:
            name: Extension name

        Returns:
            True if disabled, False if not found
        """
        extension = self._extension_map.get(name)
        if extension:
            extension.enabled = False
            logger.info("[Issue #658] Disabled extension '%s'", name)
            return True
        return False

    def load_extensions(
        self,
        extension_classes: List[Type[Extension]],
    ) -> int:
        """
        Load multiple extensions from class list.

        Args:
            extension_classes: List of Extension subclasses

        Returns:
            Number of successfully registered extensions
        """
        count = 0
        for cls in extension_classes:
            try:
                extension = cls()
                if self.register(extension):
                    count += 1
            except Exception as e:
                logger.error(
                    "[Issue #658] Failed to instantiate extension %s: %s",
                    cls.__name__,
                    str(e),
                )
        return count

    async def invoke_hook(
        self,
        hook: HookPoint,
        context: HookContext,
    ) -> List[Any]:
        """
        Invoke all extensions for a hook point.

        Each extension's hook method is called in priority order.
        Results are collected and returned.

        Args:
            hook: The hook point to invoke
            context: Hook context with relevant data

        Returns:
            List of non-None results from extensions
        """
        results = []

        for extension in self.extensions:
            if not extension.enabled:
                continue

            try:
                result = await extension.on_hook(hook, context)
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.error(
                    "[Issue #658] Extension %s failed on %s: %s",
                    extension.name,
                    hook.name,
                    str(e),
                )
                # Continue with other extensions - don't let one failure stop all

        return results

    async def invoke_until_handled(
        self,
        hook: HookPoint,
        context: HookContext,
    ) -> Optional[Any]:
        """
        Invoke extensions until one returns a truthy value.

        Useful for hooks where only one extension should handle
        (e.g., auto-approval).

        Args:
            hook: The hook point to invoke
            context: Hook context with relevant data

        Returns:
            First truthy result or None if no handler
        """
        for extension in self.extensions:
            if not extension.enabled:
                continue

            try:
                result = await extension.on_hook(hook, context)
                if result:
                    logger.debug(
                        "[Issue #658] Hook %s handled by extension '%s'",
                        hook.name,
                        extension.name,
                    )
                    return result
            except Exception as e:
                logger.error(
                    "[Issue #658] Extension %s failed on %s: %s",
                    extension.name,
                    hook.name,
                    str(e),
                )

        return None

    async def invoke_with_transform(
        self,
        hook: HookPoint,
        context: HookContext,
        key: str,
    ) -> Any:
        """
        Invoke hook and apply transformations to a specific value.

        Each extension can modify the value at `key` in context.
        Final transformed value is returned.

        Args:
            hook: The hook point to invoke
            context: Hook context with data[key] to transform
            key: The data key to transform

        Returns:
            Final transformed value
        """
        original_value = context.get(key)

        for extension in self.extensions:
            if not extension.enabled:
                continue

            try:
                result = await extension.on_hook(hook, context)
                if result is not None:
                    # Extension returned a modified value
                    context.set(key, result)
            except Exception as e:
                logger.error(
                    "[Issue #658] Extension %s failed on %s: %s",
                    extension.name,
                    hook.name,
                    str(e),
                )

        return context.get(key, original_value)

    async def invoke_cancellable(
        self,
        hook: HookPoint,
        context: HookContext,
    ) -> bool:
        """
        Invoke hook that can be cancelled by returning False.

        If any extension returns False, the operation is cancelled.

        Args:
            hook: The hook point to invoke
            context: Hook context with relevant data

        Returns:
            True if operation should proceed, False if cancelled
        """
        for extension in self.extensions:
            if not extension.enabled:
                continue

            try:
                result = await extension.on_hook(hook, context)
                if result is False:  # Explicit False check
                    logger.info(
                        "[Issue #658] Operation cancelled by extension '%s' at %s",
                        extension.name,
                        hook.name,
                    )
                    return False
            except Exception as e:
                logger.error(
                    "[Issue #658] Extension %s failed on %s: %s",
                    extension.name,
                    hook.name,
                    str(e),
                )

        return True

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about registered extensions.

        Returns:
            Dictionary with extension counts and details
        """
        enabled_count = sum(1 for e in self.extensions if e.enabled)
        disabled_count = len(self.extensions) - enabled_count

        return {
            "total_extensions": len(self.extensions),
            "enabled_count": enabled_count,
            "disabled_count": disabled_count,
            "extensions": [
                {
                    "name": e.name,
                    "priority": e.priority,
                    "enabled": e.enabled,
                }
                for e in self.extensions
            ],
        }

    def list_extensions(self) -> List[str]:
        """
        List all registered extension names.

        Returns:
            List of extension names in priority order
        """
        return [e.name for e in self.extensions]


# Singleton instance for global access (Issue #662: thread-safe)
_global_manager: Optional[ExtensionManager] = None
_global_manager_lock = threading.Lock()


def get_extension_manager() -> ExtensionManager:
    """
    Get the global extension manager instance (thread-safe).

    Returns:
        Global ExtensionManager singleton
    """
    global _global_manager
    if _global_manager is None:
        with _global_manager_lock:
            # Double-check after acquiring lock
            if _global_manager is None:
                _global_manager = ExtensionManager()
    return _global_manager


def reset_extension_manager() -> None:
    """Reset the global extension manager (for testing)."""
    global _global_manager
    with _global_manager_lock:
        _global_manager = None
