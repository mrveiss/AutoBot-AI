# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for AutoResearchConfig's canonical project-root fallbacks (#13149).

``autoresearch_dir`` and ``data_dir`` used to fall back to hardcoded
``/opt/autobot/autoresearch[...]`` literals whenever the corresponding SSOT
config value was unset or blank. A dev checkout with no
``AUTOBOT_AUTORESEARCH_DIR``/``AUTOBOT_AUTORESEARCH_DATA_DIR`` set therefore
pointed the autoresearch runner at the live install. Both now fall back to
``autobot_shared.paths.project_root()``.

Both fields are ``default_factory`` lambdas evaluated lazily at instance
construction (not at module import), so these tests build a fresh
``AutoResearchConfig()`` per case rather than reloading the module.
"""

from __future__ import annotations

from pathlib import Path

from autobot_shared.paths import project_root
from autobot_shared.ssot_config import config
from services.autoresearch.config import AutoResearchConfig


def _clear_ssot_overrides(monkeypatch) -> None:
    """Force both SSOT fields blank, exercising the ``or <fallback>`` branch
    regardless of what the host running the test has configured."""
    monkeypatch.setattr(config.misc, "autoresearch_dir", "")
    monkeypatch.setattr(config.misc, "autoresearch_data_dir", "")


def test_autoresearch_dir_is_not_the_live_install(monkeypatch):
    """The property that matters: a dev run must not resolve under /opt/autobot."""
    _clear_ssot_overrides(monkeypatch)

    cfg = AutoResearchConfig()

    assert not str(cfg.autoresearch_dir).startswith("/opt/autobot")


def test_data_dir_is_not_the_live_install(monkeypatch):
    _clear_ssot_overrides(monkeypatch)

    cfg = AutoResearchConfig()

    assert not str(cfg.data_dir).startswith("/opt/autobot")


def test_autoresearch_dir_is_wired_to_the_canonical_resolver(monkeypatch):
    _clear_ssot_overrides(monkeypatch)

    cfg = AutoResearchConfig()

    assert cfg.autoresearch_dir == project_root() / "autoresearch"


def test_data_dir_is_wired_to_the_canonical_resolver(monkeypatch):
    _clear_ssot_overrides(monkeypatch)

    cfg = AutoResearchConfig()

    assert cfg.data_dir == project_root() / "autoresearch" / "data"


def test_ssot_override_still_wins_over_the_fallback(monkeypatch, tmp_path):
    """The fallback only fires when the SSOT value is blank — an explicit
    operator setting must still take priority, exactly as before."""
    explicit = tmp_path / "explicit-autoresearch"
    monkeypatch.setattr(config.misc, "autoresearch_dir", str(explicit))
    monkeypatch.setattr(config.misc, "autoresearch_data_dir", "")

    cfg = AutoResearchConfig()

    assert cfg.autoresearch_dir == Path(str(explicit))


def test_deployed_install_still_resolves_to_the_original_default(monkeypatch):
    """Compositional check for the deployed case — see the equivalent test in
    ``source_paths_test.py`` for why AUTOBOT_PROJECT_ROOT stands in for the
    real ``.env``-walk here, and why full host verification is out of scope
    for a hermetic test.
    """
    _clear_ssot_overrides(monkeypatch)
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", "/opt/autobot")

    cfg = AutoResearchConfig()

    assert cfg.autoresearch_dir == Path("/opt/autobot/autoresearch")
    assert cfg.data_dir == Path("/opt/autobot/autoresearch/data")
