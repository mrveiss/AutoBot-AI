# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Extension Hooks System.

Issue #658: Implements Agent Zero's extension pattern with 24 lifecycle
hook points for modular customization of agent behavior.

Issue #4202: Introduces HookInvoker for centralized, extensible hook
invocation strategy with declarative configuration modes.

This package provides:
- HookPoint enum with 24 lifecycle points
- Extension base class for creating extensions
- ExtensionManager for registration and invocation
- HookInvoker for centralized, configurable hook invocation
- Built-in extensions (logging, secret_masking)

Usage (HookInvoker pattern - Issue #4202):
    from extensions import (
        HookPoint,
        Extension,
        HookContext,
        HookInvoker,
        get_extension_manager,
    )

    # Get invoker
    manager = get_extension_manager()
    invoker = HookInvoker(manager)

    # Invoke with strategy
    ctx = HookContext(session_id="sess-123", message="Hello")
    results = await invoker.invoke(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)

    # Register custom extension
    class MyExtension(Extension):
        name = "my_extension"

        async def on_before_tool_execute(self, ctx: HookContext):
            # Custom logic
            pass

    manager.register(MyExtension())

Legacy usage (direct manager):
    manager = get_extension_manager()
    await manager.invoke_hook(HookPoint.BEFORE_MESSAGE_PROCESS, ctx)
"""

from extensions.base import Extension, HookContext
from extensions.hook_invoker import (
    HookInvocationConfig,
    HookInvoker,
    InvocationMode,
)
from extensions.hooks import HOOK_METADATA, HookPoint, get_hook_metadata
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
    # HookInvoker (Issue #4202)
    "HookInvoker",
    "HookInvocationConfig",
    "InvocationMode",
]
