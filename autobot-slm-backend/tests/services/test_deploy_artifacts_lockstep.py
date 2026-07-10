# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11459: the rsync-exclude builder and the drift checker must stay in lockstep.

Both consume services/deploy_artifacts.py. These tests pin that contract so the
two paths can never re-diverge the way they did on ``*.egg-info`` (drift-skipped
in #11440 but still rsync-churned) — the exact failure #11459 consolidates.

drift_checker.py is loaded via importlib the same way drift_checker_test.py does
(without triggering the heavy services/__init__.py chain); deploy_artifacts.py is
pure-stdlib and loads standalone. A stub ``services.git_tracker`` is registered
so drift_checker's own top-level import resolves.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_SERVICES = Path(__file__).resolve().parents[2] / "services"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# deploy_artifacts is dependency-free — load it and register it so drift_checker's
# ``from services.deploy_artifacts import ...`` resolves during standalone load.
deploy_artifacts = _load("services.deploy_artifacts", _SERVICES / "deploy_artifacts.py")
if "services" not in sys.modules:
    _svc_pkg = types.ModuleType("services")
    _svc_pkg.__path__ = [str(_SERVICES)]  # type: ignore[attr-defined]
    sys.modules["services"] = _svc_pkg
sys.modules["services.deploy_artifacts"] = deploy_artifacts
if "services.git_tracker" not in sys.modules:
    _gt = types.ModuleType("services.git_tracker")
    _gt.DEFAULT_REPO_PATH = "/opt/autobot/code_source"  # type: ignore[attr-defined]
    sys.modules["services.git_tracker"] = _gt

drift_checker = _load("drift_checker", _SERVICES / "drift_checker.py")

ARTIFACT_DIRS = deploy_artifacts.ARTIFACT_DIRS
ARTIFACT_DIR_SUFFIXES = deploy_artifacts.ARTIFACT_DIR_SUFFIXES
ARTIFACT_FILE_GLOBS = deploy_artifacts.ARTIFACT_FILE_GLOBS
rsync_artifact_excludes = deploy_artifacts.rsync_artifact_excludes


def test_rsync_excludes_cover_every_drift_skip_dir() -> None:
    """Every dir the drift walk prunes must also be an rsync --exclude pattern.

    If a dir is skipped by drift but synced by rsync (or vice-versa) the two
    disagree about what an artifact is — the #11440 egg-info bug generalised.
    """
    excludes = set(rsync_artifact_excludes())
    for skip_dir in drift_checker._SKIP_DIRS:
        assert skip_dir in excludes, f"drift skips {skip_dir!r} but rsync would sync it"


def test_egg_info_excluded_by_both_paths() -> None:
    """*.egg-info is the concrete regression (#11440/#11459) — pin it in both."""
    assert ".egg-info" in drift_checker._SKIP_DIR_SUFFIXES
    assert "*.egg-info" in rsync_artifact_excludes()


def test_drift_checker_derives_from_canonical_source() -> None:
    """drift_checker must consume the shared vocabulary, not a private copy."""
    assert drift_checker._SKIP_DIRS == set(ARTIFACT_DIRS)
    assert drift_checker._SKIP_DIR_SUFFIXES == ARTIFACT_DIR_SUFFIXES


def test_rsync_artifact_excludes_shape() -> None:
    """The rsync pattern list covers dir names, suffix globs, and file globs."""
    patterns = rsync_artifact_excludes()
    assert "__pycache__" in patterns and "node_modules" in patterns
    for suffix in ARTIFACT_DIR_SUFFIXES:
        assert f"*{suffix}" in patterns
    for glob in ARTIFACT_FILE_GLOBS:
        assert glob in patterns
    assert len(patterns) == len(set(patterns)), "no duplicate --exclude patterns"
