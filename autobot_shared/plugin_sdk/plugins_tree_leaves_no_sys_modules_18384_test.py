# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Running the plugin trees' tests must leave no ``plugins`` package behind (#18384).

The loader's file-path fallback skips any parent package already in
``sys.modules``, so a ``plugins`` namespace left by the plugin trees' own tests
changed what ``loader_file_fallback_test.py`` saw. That is only observable across
modules, so this runs both in ONE fresh pytest process, in each order.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("plugins_conftest_18384", _ROOT / "plugins" / "conftest.py")
_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_conftest)
withdraw_plugins_packages = _conftest.withdraw_plugins_packages

_LOADER = "autobot_shared/plugin_sdk/loader_file_fallback_test.py"
_TREES = ("plugins/core-plugins/image-generation-plugin", "plugins/core-plugins/video-generation-plugin")


@pytest.mark.parametrize("trees_first", [True, False])
def test_the_loader_tests_pass_after_and_before_the_plugin_trees(trees_first):
    args = [*_TREES, _LOADER] if trees_first else [_LOADER, *_TREES]
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:randomly", "-p", "no:cacheprovider", "-q", *args],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-1000:]


def test_withdraw_removes_every_plugins_entry_and_nothing_else(monkeypatch):
    # Entries other tests in this process (the loader's) legitimately left are set aside, then restored.
    for name in [n for n in sys.modules if n == "plugins" or n.startswith("plugins.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "plugins", sys)
    monkeypatch.setitem(sys.modules, "plugins.core-plugins", sys)
    monkeypatch.setitem(sys.modules, "pluginsx", sys)
    assert sorted(withdraw_plugins_packages()) == ["plugins", "plugins.core-plugins"]
    assert "pluginsx" in sys.modules
