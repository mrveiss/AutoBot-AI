# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The credential resolver follows a plugin's verified origin, not its self-declared name (#18094)."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk.credential_binding import bound_resolver
from autobot_shared.plugin_sdk.loader import PluginLoader

_CORE = Path(__file__).resolve().parents[2] / "plugins" / "core-plugins"
_NAME = "image-generation-plugin"
_SENTINEL = "never-logged-sentinel-7c4a8d09"  # pragma: allowlist secret


def _resolver(name: str) -> str:
    return _SENTINEL


@pytest.fixture(autouse=True)
def _restore_sys_modules():
    before = dict(sys.modules)
    yield
    for key in set(sys.modules) - set(before):
        del sys.modules[key]
    # canonicalise_plugin_sdk() REPLACES existing `plugin_sdk.*` entries with aliases of the
    # canonical modules; a key-set diff misses those, so put every replaced value back too.
    for key, module in before.items():
        if sys.modules.get(key) is not module:
            sys.modules[key] = module


@pytest.fixture
def impostor_root(tmp_path: Path) -> Path:
    """A community-plugins dir holding a copy of the plugin that claims the built-in's name."""
    root = tmp_path / "community-plugins"
    shutil.copytree(_CORE / _NAME, root / _NAME)
    return root


async def _load(loader: PluginLoader):
    manifest = next(m for m in loader.discover_plugins() if m.name == _NAME)
    plugin = await loader.load_plugin(manifest)
    assert plugin is not None
    await loader.unload_plugin(_NAME)
    return plugin


@pytest.mark.asyncio
async def test_a_community_plugin_with_the_builtin_name_gets_no_resolver(impostor_root, tmp_path, caplog) -> None:
    missing_core = tmp_path / "core-plugins-absent"
    loader = PluginLoader([missing_core, impostor_root], {_NAME: _resolver}, [missing_core])
    with caplog.at_level(logging.WARNING):
        plugin = await _load(loader)
    assert plugin.credential_resolver is None
    assert _NAME in caplog.text and _SENTINEL not in caplog.text


@pytest.mark.asyncio
async def test_an_empty_core_dir_does_not_let_the_impostor_in(impostor_root, tmp_path) -> None:
    empty_core = tmp_path / "core-plugins"
    empty_core.mkdir()
    loader = PluginLoader([empty_core, impostor_root], {_NAME: _resolver}, [empty_core])
    assert (await _load(loader)).credential_resolver is None


@pytest.mark.asyncio
async def test_no_trusted_roots_means_no_resolver() -> None:
    loader = PluginLoader([_CORE], {_NAME: _resolver})
    assert (await _load(loader)).credential_resolver is None


def test_a_symlink_from_core_to_a_community_plugin_does_not_qualify(impostor_root, tmp_path) -> None:
    core = tmp_path / "core-plugins"
    core.mkdir()
    link = core / _NAME
    link.symlink_to(impostor_root / _NAME, target_is_directory=True)
    assert bound_resolver(_NAME, link, {_NAME: _resolver}, [core]) is None
    assert bound_resolver(_NAME, _CORE / _NAME, {_NAME: _resolver}, [_CORE]) is _resolver
    assert bound_resolver(_NAME, None, {_NAME: _resolver}, [_CORE]) is None


@pytest.mark.asyncio
async def test_the_genuine_core_plugin_still_gets_its_resolver() -> None:
    loader = PluginLoader([_CORE], {_NAME: _resolver}, [_CORE])
    assert (await _load(loader)).credential_resolver is _resolver
