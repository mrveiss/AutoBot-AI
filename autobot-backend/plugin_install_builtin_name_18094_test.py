# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A community install may not take a built-in plugin's name (#18094)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import plugin_install

_MANIFEST = {
    "name": "builtin-demo",
    "display_name": "Builtin Demo",
    "description": "d",
    "author": "mrveiss",
    "entry_point": "plugins.builtin_demo.main",
}


@pytest.fixture
def plugins_root(tmp_path: Path, monkeypatch) -> Path:
    core = tmp_path / "core-plugins" / "builtin-demo"
    core.mkdir(parents=True)
    (core / "plugin.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")
    monkeypatch.setattr(plugin_install, "config", SimpleNamespace(path=SimpleNamespace(plugins_path=tmp_path)))
    return tmp_path


def test_the_reserved_names_come_from_the_core_manifests(plugins_root) -> None:
    assert plugin_install._builtin_plugin_names() == {"builtin-demo"}


def test_an_install_named_like_a_builtin_is_rejected(plugins_root) -> None:
    with pytest.raises(HTTPException) as exc:
        plugin_install._sanitize_plugin_name("builtin-demo")
    assert exc.value.status_code == 409


def test_other_names_still_pass(plugins_root) -> None:
    assert plugin_install._sanitize_plugin_name("community-thing") == "community-thing"


def test_an_absent_core_dir_reserves_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(plugin_install, "config", SimpleNamespace(path=SimpleNamespace(plugins_path=tmp_path)))
    assert plugin_install._builtin_plugin_names() == set()
