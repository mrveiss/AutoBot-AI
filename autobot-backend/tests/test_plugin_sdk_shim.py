# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shim identity tests for the deduplicated plugin SDK (#11636).

The backend-local ``plugin_sdk`` package was a stale fork of
``autobot_shared.plugin_sdk``. It is now a re-export shim; these tests pin
the invariant that both import paths resolve to the SAME class objects, so
there is exactly ONE PluginRegistry / CapabilityChecker singleton at runtime.
"""

from autobot_shared.plugin_sdk import base as shared_base
from autobot_shared.plugin_sdk import capabilities as shared_capabilities
from autobot_shared.plugin_sdk import loader as shared_loader
from plugin_sdk import base as shim_base
from plugin_sdk import capabilities as shim_capabilities
from plugin_sdk import loader as shim_loader


def test_base_classes_are_identical():
    assert shim_base.PluginRegistry is shared_base.PluginRegistry
    assert shim_base.PluginManifest is shared_base.PluginManifest
    assert shim_base.BasePlugin is shared_base.BasePlugin
    assert shim_base.PluginLoadError is shared_base.PluginLoadError


def test_capability_classes_are_identical():
    assert shim_capabilities.CapabilityChecker is shared_capabilities.CapabilityChecker
    assert shim_capabilities.Capability is shared_capabilities.Capability
    assert shim_capabilities.TrustTier is shared_capabilities.TrustTier
    assert shim_capabilities.CapabilityError is shared_capabilities.CapabilityError


def test_loader_is_identical():
    assert shim_loader.PluginLoader is shared_loader.PluginLoader
    assert shim_loader.validate_plugin_config is shared_loader.validate_plugin_config


def test_registry_singleton_shared_across_import_paths():
    """Registering via one path must be visible via the other."""
    shim_registry = shim_base.PluginRegistry()
    shared_registry = shared_base.PluginRegistry()
    assert shim_registry is shared_registry


def test_capability_checker_singleton_shared_across_import_paths():
    shim_checker = shim_capabilities.CapabilityChecker()
    shared_checker = shared_capabilities.CapabilityChecker()
    assert shim_checker is shared_checker


def test_hooks_module_identical():
    """Core plugins import `plugin_sdk.hooks` — the shim must provide it."""
    from autobot_shared.plugin_sdk import hooks as shared_hooks

    from plugin_sdk import hooks as shim_hooks

    assert shim_hooks.Hook is shared_hooks.Hook
    assert shim_hooks.HookRegistry is shared_hooks.HookRegistry
    assert shim_hooks.HookSignature is shared_hooks.HookSignature
    assert shim_hooks.HOOK_REGISTRY is shared_hooks.HOOK_REGISTRY
    assert shim_hooks.validate_hook_names is shared_hooks.validate_hook_names
