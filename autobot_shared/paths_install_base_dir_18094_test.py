# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``install_base_dir``: env first, then project_root; a fallback only when the caller names one (#18094)."""

from __future__ import annotations

from pathlib import Path

import pytest

from autobot_shared import paths


def _undeterminable() -> Path:
    raise paths.ProjectRootUndeterminable("no root here")


def test_the_env_var_wins(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(paths.BASE_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(paths, "project_root", _undeterminable)
    assert paths.install_base_dir() == tmp_path


def test_without_a_named_fallback_the_raise_propagates(monkeypatch) -> None:
    monkeypatch.delenv(paths.BASE_DIR_ENV, raising=False)
    monkeypatch.setattr(paths, "project_root", _undeterminable)
    with pytest.raises(paths.ProjectRootUndeterminable):
        paths.install_base_dir()


def test_a_named_fallback_answers_only_when_undeterminable(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(paths.BASE_DIR_ENV, raising=False)
    monkeypatch.setattr(paths, "project_root", lambda: tmp_path)
    assert paths.install_base_dir(when_undeterminable="/fallback") == tmp_path

    monkeypatch.setattr(paths, "project_root", _undeterminable)
    assert paths.install_base_dir(when_undeterminable="/fallback") == Path("/fallback")
