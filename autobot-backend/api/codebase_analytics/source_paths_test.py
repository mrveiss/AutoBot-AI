# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for CODE_SOURCES_BASE's canonical project-root default (#13149).

Before this fix ``CODE_SOURCES_BASE`` was a module-level literal hardcoding
``/opt/autobot/data/code-sources`` — every dev checkout cloned code sources
into (or read them from) the live install's directory. It now derives from
``autobot_shared.paths.project_root()``.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import api.codebase_analytics.source_paths as source_paths
from autobot_shared.paths import project_root


def test_code_sources_base_is_not_the_live_install():
    """The property that matters: a dev run must not resolve under /opt/autobot."""
    assert not str(source_paths.CODE_SOURCES_BASE).startswith("/opt/autobot")


def test_code_sources_base_is_wired_to_the_canonical_resolver():
    """Not just 'some path comes back' — it must be *this checkout's* root."""
    assert source_paths.CODE_SOURCES_BASE == project_root() / "data" / "code-sources"


def test_code_sources_base_tracks_project_root_env_override(monkeypatch, tmp_path):
    """Changing AUTOBOT_PROJECT_ROOT changes the derived default, proving the
    site is actually wired through project_root() rather than re-hardcoded
    under a different name."""
    fake_root = tmp_path / "fake-checkout"
    fake_root.mkdir()
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", str(fake_root))

    reloaded = importlib.reload(source_paths)
    try:
        assert reloaded.CODE_SOURCES_BASE == fake_root / "data" / "code-sources"
    finally:
        monkeypatch.delenv("AUTOBOT_PROJECT_ROOT", raising=False)
        importlib.reload(source_paths)


def test_deployed_install_still_resolves_to_the_original_default(monkeypatch):
    """Compositional check for the deployed case.

    A real host resolves ``project_root()`` to ``/opt/autobot`` via the
    ``.env``-walk (verified separately in ``autobot_shared/paths_test.py``'s
    ``TestDeployedInstall`` and confirmed on a live host per #13149's comment
    thread). ``AUTOBOT_PROJECT_ROOT`` is the resolver's first-priority branch
    and reaches the same value without requiring a real ``/opt/autobot`` tree
    on this machine, so it is used here to prove *composition* — that when
    project_root() is ``/opt/autobot``, this call site reproduces the exact
    previous literal, byte for byte, and does not additionally break the
    deployed case with an extra path segment or a different join order.
    Confirming the resolver's own branch selection on a real deployed host is
    out of scope for a hermetic test — no host was available to verify this
    beyond that compositional guarantee.
    """
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", "/opt/autobot")

    reloaded = importlib.reload(source_paths)
    try:
        assert reloaded.CODE_SOURCES_BASE == Path("/opt/autobot/data/code-sources")
    finally:
        monkeypatch.delenv("AUTOBOT_PROJECT_ROOT", raising=False)
        importlib.reload(source_paths)
