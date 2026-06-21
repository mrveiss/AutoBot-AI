# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for the protected rsync excludes (#9970).

The deployed .env (systemd EnvironmentFile, #2824) and runtime data dirs
exist only in the deployment — a delete-style rsync without these excludes
removes them and the synced service cannot start. The protection is applied
at the rsync chokepoint (_rsync_exclude_args) so no component list or
caller can forget it.
"""

from __future__ import annotations

# Add autobot-slm-backend to path so api.code_sync imports resolve.
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from api.code_sync import (  # noqa: E402
    _PROTECTED_EXCLUDES,
    _SLM_COMPONENTS,
    _rsync_exclude_args,
)


def test_protected_excludes_cover_env_and_data() -> None:
    assert ".env" in _PROTECTED_EXCLUDES
    assert "data" in _PROTECTED_EXCLUDES


def test_exclude_args_always_include_protected_paths() -> None:
    args = _rsync_exclude_args([])
    assert "--exclude=.env" in args
    assert "--exclude=data" in args


def test_exclude_args_for_every_component_list() -> None:
    for component, excludes in _SLM_COMPONENTS:
        args = _rsync_exclude_args(excludes)
        assert "--exclude=.env" in args, f"{component} sync would delete .env"
        assert "--exclude=data" in args, f"{component} sync would delete data"
        # caller excludes are preserved
        for exc in excludes:
            assert f"--exclude={exc}" in args


def test_exclude_args_deduplicate() -> None:
    args = _rsync_exclude_args([".env", "venv", "venv"])
    assert args.count("--exclude=.env") == 1
    assert args.count("--exclude=venv") == 1
