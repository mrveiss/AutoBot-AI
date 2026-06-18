# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the generate_video tool — GH#9016. Providers are mocked."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_HERE = Path(__file__).resolve().parent


def _load(mod_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(mod_name, _HERE / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


# Load providers first so generate_video's relative import resolves.
providers = _load("vg_providers_tool_test", "providers.py")


@pytest.fixture
def tool(monkeypatch):
    """Build the GenerateVideoTool with tool_sdk stubbed (no backend deps)."""
    base = MagicMock()
    base.ToolMetadata = lambda **k: MagicMock(**k)
    base.ToolPermission = MagicMock(AUTHENTICATED="authenticated")

    class _Result:
        def __init__(self, success, data=None, error=None, duration_ms=0.0):
            self.success = success
            self.data = data
            self.error = error
            self.duration_ms = duration_ms

    base.ToolResult = _Result

    class _BaseTool:
        def __init_subclass__(cls, **k):
            super().__init_subclass__(**k)

    base.BaseTool = _BaseTool

    monkeypatch.setitem(sys.modules, "tool_sdk", MagicMock())
    monkeypatch.setitem(sys.modules, "tool_sdk.base", base)

    # Build a real package module so `from .providers import ...` resolves.
    import types

    pkg = types.ModuleType("vg_tool_pkg")
    pkg.__path__ = [str(_HERE)]  # mark as a package
    monkeypatch.setitem(sys.modules, "vg_tool_pkg", pkg)
    monkeypatch.setitem(sys.modules, "vg_tool_pkg.providers", providers)

    spec = importlib.util.spec_from_file_location("vg_tool_pkg.generate_video", _HERE / "generate_video.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vg_tool_pkg.generate_video"] = mod
    spec.loader.exec_module(mod)
    return mod.GenerateVideoTool(), mod


@pytest.mark.asyncio
async def test_generate_video_returns_url(tool, monkeypatch):
    instance, mod = tool

    fake_provider = MagicMock()
    fake_provider.name = "runway"
    fake_provider.env_var = "RUNWAY_API_KEY"
    fake_provider.available = True
    fake_provider.submit = AsyncMock(return_value="job-1")
    succeeded = providers.JobStatus("job-1", "succeeded", 1.0, video_url="https://v/c.mp4", provider="runway")
    fake_provider.poll = AsyncMock(return_value=succeeded)
    monkeypatch.setattr(mod, "get_provider", lambda name: fake_provider)

    result = await instance.execute({"prompt": "a sunrise", "duration": 5})
    assert result.success is True
    assert result.data["video_url"] == "https://v/c.mp4"
    assert result.data["provider"] == "runway"
    assert result.data["job_id"] == "job-1"


@pytest.mark.asyncio
async def test_generate_video_provider_disabled(tool, monkeypatch):
    instance, mod = tool
    disabled = MagicMock()
    disabled.available = False
    disabled.env_var = "RUNWAY_API_KEY"
    monkeypatch.setattr(mod, "get_provider", lambda name: disabled)

    result = await instance.execute({"prompt": "x", "provider": "runway"})
    assert result.success is False
    assert "RUNWAY_API_KEY" in result.error


@pytest.mark.asyncio
async def test_generate_video_failure(tool, monkeypatch):
    instance, mod = tool
    fake = MagicMock()
    fake.name = "runway"
    fake.available = True
    fake.submit = AsyncMock(return_value="job-2")
    failed = providers.JobStatus("job-2", "failed", 0.0, error="moderation", provider="runway")
    fake.poll = AsyncMock(return_value=failed)
    monkeypatch.setattr(mod, "get_provider", lambda name: fake)

    result = await instance.execute({"prompt": "x"})
    assert result.success is False
    assert "moderation" in result.error
