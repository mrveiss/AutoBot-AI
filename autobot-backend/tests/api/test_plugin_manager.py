# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for the plugin manager FastAPI endpoints (Issue #6971).

Covers GET /plugins/{plugin_name}/env-status — env-var configuration
status without leaking values.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_env_status_endpoint_returns_status_for_loaded_plugin(monkeypatch):
    from plugin_manager import get_plugin_env_status

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
async def test_env_status_endpoint_404_for_unknown_plugin(monkeypatch):
    from plugin_manager import get_plugin_env_status

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
async def test_env_status_endpoint_returns_empty_for_plugin_without_required_env(monkeypatch):
    from plugin_manager import get_plugin_env_status

    fake_loader = MagicMock()
    fake_loader.get_env_status.return_value = {}

    with patch("plugin_manager.get_plugin_loader", return_value=fake_loader):
        result = await get_plugin_env_status(
            plugin_name="simple-plugin",
            admin_check=True,
        )

    assert result.plugin_name == "simple-plugin"
    assert result.env_vars == {}
