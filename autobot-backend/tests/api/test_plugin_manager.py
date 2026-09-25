# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the plugin manager FastAPI endpoints (Issue #6971).

Covers GET /plugins/{plugin_name}/env-status — env-var configuration
status without leaking values.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from plugin_manager import get_plugin_env_status, load_plugin


@pytest.mark.asyncio
async def test_env_status_endpoint_returns_status_for_loaded_plugin():
    fake_loader = MagicMock()
    fake_loader.get_env_status.return_value = {
        "MY_API_KEY": {
            "configured": True,
            "secret": True,
            "required": False,
            "description": "API key",
            "docs_url": "https://example.com/keys",
            "obtain_steps": ["Sign in", "Generate"],
        }
    }

    with patch("plugin_manager.get_plugin_loader", return_value=fake_loader):
        result = await get_plugin_env_status(
            plugin_name="my-plugin",
            admin_check=True,
        )

    assert result.plugin_name == "my-plugin"
    assert "MY_API_KEY" in result.env_vars
    entry = result.env_vars["MY_API_KEY"]
    assert entry.configured is True
    assert entry.secret is True
    assert entry.docs_url == "https://example.com/keys"
    assert entry.obtain_steps == ["Sign in", "Generate"]


@pytest.mark.asyncio
async def test_env_status_endpoint_404_for_unknown_plugin():
    fake_loader = MagicMock()
    fake_loader.get_env_status.return_value = None

    with patch("plugin_manager.get_plugin_loader", return_value=fake_loader):
        with pytest.raises(HTTPException) as exc_info:
            await get_plugin_env_status(
                plugin_name="does-not-exist",
                admin_check=True,
            )

    assert exc_info.value.status_code == 404
    assert "does-not-exist" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_env_status_endpoint_returns_empty_for_plugin_without_required_env():
    fake_loader = MagicMock()
    fake_loader.get_env_status.return_value = {}

    with patch("plugin_manager.get_plugin_loader", return_value=fake_loader):
        result = await get_plugin_env_status(
            plugin_name="simple-plugin",
            admin_check=True,
        )

    assert result.plugin_name == "simple-plugin"
    assert result.env_vars == {}


@pytest.mark.asyncio
async def test_env_status_endpoint_with_real_loader_no_mock(monkeypatch):
    """Integration test: real PluginLoader -> real RequiredEnvVar -> endpoint.

    Catches contract drift between get_env_status's dict shape and
    PluginEnvStatusEntry's expected fields. If the dict ever loses a
    field or gains an unrelated one, this test fails at the
    PluginEnvStatusEntry(**v) boundary.
    """
    from autobot_shared.plugin_sdk.base import PluginManifest, PluginRegistry, PluginStatus
    from autobot_shared.plugin_sdk.loader import PluginLoader

    # Set the real env var so configured=True
    monkeypatch.setenv("REAL_INTEGRATION_VAR", "any_value")

    # Build a real plugin manifest with one required_env entry
    manifest = PluginManifest(
        name="real-plugin-integration",
        version="1.0.0",
        display_name="Real Plugin",
        description="Integration test plugin.",
        author="test",
        entry_point="test.module",
        required_env=[
            {
                "name": "REAL_INTEGRATION_VAR",
                "description": "Integration test var.",
                "secret": True,
                "required": True,
                "docs_url": "https://example.com/docs",
                "obtain_steps": ["step1", "step2"],
            }
        ],
    )

    # Register a stub plugin into the real registry so get_env_status finds it
    PluginRegistry().clear()

    class _StubPlugin:
        def __init__(self, manifest):
            self.manifest = manifest
            self.status = PluginStatus.LOADED

    stub_plugin = _StubPlugin(manifest)
    PluginRegistry().register(stub_plugin)

    # Real loader, no mocks
    real_loader = PluginLoader([])

    with patch("plugin_manager.get_plugin_loader", return_value=real_loader):
        result = await get_plugin_env_status(
            plugin_name="real-plugin-integration",
            admin_check=True,
        )

    # If the loader's dict shape drifts, PluginEnvStatusEntry(**v) raises
    # a ValidationError before this assertion is reached
    assert result.plugin_name == "real-plugin-integration"
    assert "REAL_INTEGRATION_VAR" in result.env_vars
    entry = result.env_vars["REAL_INTEGRATION_VAR"]
    assert entry.configured is True
    assert entry.secret is True
    assert entry.required is True
    assert entry.description == "Integration test var."
    assert entry.docs_url == "https://example.com/docs"
    assert entry.obtain_steps == ["step1", "step2"]


# --- Issue #17420: manual plugin-load path -------------------------------
#
# Regression coverage for a two-part defect:
#   1. Signature mismatch — plugin_manager.load_plugin passed
#      grant_capabilities= to loader.load_plugin, which accepts no such
#      argument, so every manual load raised TypeError.
#   2. #9049 auto-grant contract — official plugins should auto-grant on
#      load; non-official plugins must remain ungranted until an operator
#      approves them via /approve-capabilities.


def _make_load_endpoint_mocks(trust_tier, capabilities):
    """Build the mocks used by every manual-load test.

    Returns (loader_mock, manifest_mock, loaded_plugin) so each test can
    assert on the call surface it cares about.
    """
    from autobot_shared.plugin_sdk.base import PluginManifest

    manifest = MagicMock(spec=PluginManifest)
    manifest.name = "test-plugin"
    manifest.trust_tier = trust_tier
    manifest.capabilities = capabilities

    loaded_plugin = MagicMock()
    loaded_plugin.name = "test-plugin"

    loader = MagicMock()
    loader.discover_plugins.return_value = [manifest]
    loader.load_plugin = AsyncMock(return_value=loaded_plugin)

    return loader, manifest, loaded_plugin


@pytest.mark.asyncio
async def test_load_plugin_endpoint_does_not_pass_grant_capabilities_kwarg():
    """Mutation guard for #17420.

    loader.load_plugin(manifest, config, grant_capabilities=...) would
    TypeError at runtime; the endpoint must call it with positional
    manifest + config only.
    """
    from autobot_shared.plugin_sdk.capabilities import Capability, TrustTier

    loader, _, _ = _make_load_endpoint_mocks(TrustTier.COMMUNITY, [Capability.KB_READ])

    with (
        patch("plugin_manager.get_plugin_loader", return_value=loader),
        patch("plugin_manager._save_plugin_config", new=AsyncMock()),
        patch("plugin_manager.CapabilityChecker"),
    ):
        await load_plugin(plugin_name="test-plugin", config=None, admin_check=True)

    loader.load_plugin.assert_awaited_once()
    _, kwargs = loader.load_plugin.call_args
    assert "grant_capabilities" not in kwargs, (
        "loader.load_plugin does not accept grant_capabilities kwarg — " "passing it raises TypeError (#17420)"
    )


@pytest.mark.asyncio
async def test_load_plugin_endpoint_auto_grants_official_plugin_capabilities():
    """#9049 contract: official plugins auto-grant on load."""
    from autobot_shared.plugin_sdk.capabilities import Capability, TrustTier

    granted = [Capability.KB_READ, Capability.LLM_CALL]
    loader, manifest, _ = _make_load_endpoint_mocks(TrustTier.OFFICIAL, granted)

    with (
        patch("plugin_manager.get_plugin_loader", return_value=loader),
        patch("plugin_manager._save_plugin_config", new=AsyncMock()),
        patch("plugin_manager.CapabilityChecker") as checker_cls,
    ):
        checker_instance = checker_cls.return_value
        result = await load_plugin(plugin_name="test-plugin", config=None, admin_check=True)

    assert result["status"] == "success"
    checker_instance.grant_capabilities.assert_called_once_with("test-plugin", granted)


@pytest.mark.asyncio
async def test_load_plugin_endpoint_does_not_auto_grant_community_plugin():
    """#9049 contract: non-official plugins are NOT auto-granted.

    Positive control for the OFFICIAL test above — proves the endpoint is
    actually gating on trust_tier, not blindly granting every load.
    """
    from autobot_shared.plugin_sdk.capabilities import Capability, TrustTier

    loader, _, _ = _make_load_endpoint_mocks(TrustTier.COMMUNITY, [Capability.KB_READ])

    with (
        patch("plugin_manager.get_plugin_loader", return_value=loader),
        patch("plugin_manager._save_plugin_config", new=AsyncMock()),
        patch("plugin_manager.CapabilityChecker") as checker_cls,
    ):
        checker_instance = checker_cls.return_value
        result = await load_plugin(plugin_name="test-plugin", config=None, admin_check=True)

    assert result["status"] == "success"
    checker_instance.grant_capabilities.assert_not_called()
