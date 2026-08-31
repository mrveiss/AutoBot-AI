# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A logging plugin that cannot open its log file is still a plugin (#13967).

`logger-plugin` wrote to `/tmp/plugin_events.log` — a fixed name in a shared,
world-writable directory. The first user to create it owns it, and every other
user on the host gets PermissionError. Two problems, and the second is the one
that matters: `initialize()` had no error handling, so an environment condition
took the whole plugin down rather than degrading it.

Found while fixing #13677: with that PR and #10294 core plugins go from 0-of-7
to 5-of-7, and this is one of the two remaining failures — previously
indistinguishable from the other five, which is exactly what #13677's
`loaded N of M` signal now separates.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Deliberately NOT co-located with the plugin: collecting a test from under
# `plugins/` puts a real `plugins` module into sys.modules, which is precisely
# what #10294's synthetic-namespace guards assert must not happen. The module is
# loaded by absolute path, so location is irrelevant to what is exercised.
_MAIN = Path(__file__).resolve().parents[2] / "plugins" / "core-plugins" / "logger-plugin" / "main.py"


def _load_module():
    """Load the plugin module by path — it is not on sys.path as a package."""
    spec = importlib.util.spec_from_file_location("logger_plugin_main_13967", _MAIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def mod():
    module = _load_module()
    yield module
    sys.modules.pop("logger_plugin_main_13967", None)


class TestDefaultPathIsNotShared:
    def test_the_default_is_not_the_shared_tmp_name(self, mod, monkeypatch):
        monkeypatch.delenv("AUTOBOT_LOG_DIR", raising=False)
        path = mod._default_log_path()
        assert str(path) != "/tmp/plugin_events.log", "a fixed name in a shared dir locks out every other user"

    def test_the_default_is_per_user_when_it_must_fall_back_to_tmp(self, mod, monkeypatch):
        monkeypatch.delenv("AUTOBOT_LOG_DIR", raising=False)
        path = mod._default_log_path()
        assert str(os.getuid()) in str(path), "a /tmp fallback must be per-user or it recreates the collision"

    def test_the_configured_log_directory_wins(self, mod, monkeypatch, tmp_path):
        monkeypatch.setenv("AUTOBOT_LOG_DIR", str(tmp_path))
        assert mod._default_log_path() == tmp_path / "plugin_events.log"


class TestInitializeDegrades:
    @pytest.mark.asyncio
    async def test_an_unwritable_path_disables_the_sink_rather_than_the_plugin(self, mod, tmp_path, monkeypatch):
        from autobot_shared.plugin_sdk.base import PluginManifest

        manifest = PluginManifest(
            name="logger-plugin",
            version="1.0.0",
            display_name="Logger",
            description="d",
            author="mrveiss",
            entry_point="main",
        )
        plugin = mod.LoggerPlugin(manifest, {"log_file": str(tmp_path / "nope" / "events.log")})

        def _boom(*_a, **_k):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(Path, "mkdir", _boom)

        await plugin.initialize()

        assert plugin._sink_enabled is False, "the plugin must survive an unwritable log path"

    @pytest.mark.asyncio
    async def test_a_writable_path_keeps_the_sink_enabled(self, mod, tmp_path):
        """The direction that must stay true — a sink that is always disabled
        would pass the test above while breaking the plugin's whole purpose."""
        from autobot_shared.plugin_sdk.base import PluginManifest

        manifest = PluginManifest(
            name="logger-plugin",
            version="1.0.0",
            display_name="Logger",
            description="d",
            author="mrveiss",
            entry_point="main",
        )
        target = tmp_path / "events.log"
        plugin = mod.LoggerPlugin(manifest, {"log_file": str(target)})

        await plugin.initialize()

        assert plugin._sink_enabled is True
        assert target.exists()

    def test_a_disabled_sink_does_not_flood_the_log(self, mod, tmp_path):
        """Reporting per event would turn a degraded sink into a log flood."""
        from autobot_shared.plugin_sdk.base import PluginManifest

        manifest = PluginManifest(
            name="logger-plugin",
            version="1.0.0",
            display_name="Logger",
            description="d",
            author="mrveiss",
            entry_point="main",
        )
        plugin = mod.LoggerPlugin(manifest, {"log_file": str(tmp_path / "events.log")})
        plugin._sink_enabled = False

        plugin._write_log({"event": "x"})

        assert not (tmp_path / "events.log").exists()
