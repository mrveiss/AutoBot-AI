# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""File-path import fallback for core plugins — Issue #10294.

Core plugins live in hyphenated dirs (plugins/core-plugins/hello-plugin) whose
dotted entry_point (plugins.core_plugins.hello_plugin.main) is not importable.
The loader must fall back to importing main.py by file path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk.loader import PluginLoader

_PLUGIN_MAIN = '''
from autobot_shared.plugin_sdk.base import BasePlugin


class SamplePlugin(BasePlugin):
    async def initialize(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None


# No "Plugin" alias on purpose — loader finds the BasePlugin subclass.
'''


def _write_plugin(root: Path, dir_name: str, entry_point: str) -> Path:
    pdir = root / dir_name
    pdir.mkdir(parents=True)
    (pdir / "main.py").write_text(_PLUGIN_MAIN, encoding="utf-8")
    manifest = {
        "name": dir_name,
        "version": "1.0.0",
        "display_name": "Sample",
        "description": "sample",
        "author": "test",
        "entry_point": entry_point,
    }
    (pdir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pdir


@pytest.mark.asyncio
async def test_hyphenated_plugin_loads_via_file_path(tmp_path: Path) -> None:
    """A hyphenated dir whose dotted entry_point is not importable still loads."""
    root = tmp_path / "core-plugins"
    _write_plugin(root, "hello-plugin", "plugins.core_plugins.hello_plugin.main")

    loader = PluginLoader([root])
    manifests = loader.discover_plugins()
    assert len(manifests) == 1
    assert loader._manifest_dirs["hello-plugin"].name == "hello-plugin"

    plugin = await loader.load_plugin(manifests[0])
    assert plugin is not None
    assert type(plugin).__name__ == "SamplePlugin"


def test_import_from_file_missing_dir_returns_none(tmp_path: Path) -> None:
    loader = PluginLoader([])
    assert loader._import_from_file("plugins.core_plugins.x.main", None) is None
    assert loader._import_from_file("plugins.core_plugins.x.main", tmp_path) is None
