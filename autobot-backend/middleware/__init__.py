# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Middleware package — extension lifecycle hooks system.

Re-exports all public symbols from submodules so callers can import from
``middleware`` directly:

    from middleware import Extension, HookPoint, get_extension_manager

The ``extensions`` package re-exports these under its own namespace for
backwards compatibility (#7426).
"""

from middleware.base import Extension, HookContext
from middleware.hook_invoker import HookInvocationConfig, HookInvoker, InvocationMode
from middleware.hooks import HOOK_METADATA, HookPoint, get_hook_metadata
from middleware.manager import ExtensionManager, get_extension_manager, reset_extension_manager

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
