# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Extension Hooks System.

Issue #658: Implements Agent Zero's extension pattern with 22 lifecycle
hook points for modular customization of agent behavior.

This package provides:
- HookPoint enum with 22 lifecycle points
- Extension base class for creating extensions
- ExtensionManager for registration and invocation
- Built-in extensions (logging, secret_masking)

Usage:
    from extensions import (
        HookPoint,
        Extension,
        HookContext,
        ExtensionManager,
        get_extension_manager,
    )

    # Get global manager
    manager = get_extension_manager()

    # Register custom extension
    class MyExtension(Extension):
        name = "my_extension"

        async def on_before_tool_execute(self, ctx: HookContext):
            # Custom logic
            pass

    manager.register(MyExtension())

    # Invoke hook
    ctx = HookContext(session_id="sess-123", message="Hello")
    await manager.invoke_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)
"""

from extensions.base import Extension, HookContext
from extensions.hooks import HookPoint, get_hook_metadata, HOOK_METADATA
from extensions.manager import (
    ExtensionManager,
    get_extension_manager,
    reset_extension_manager,
)

__all__ = [
    # Hook definitions
    "HookPoint",
    "HOOK_METADATA",
    "get_hook_metadata",
    # Base classes
    "Extension",
    "HookContext",
    # Manager
    "ExtensionManager",
    "get_extension_manager",
    "reset_extension_manager",
]
