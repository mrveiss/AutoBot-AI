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

import sys
from pathlib import Path

# #12572: import api.code_sync via the shared helper, which installs real
# Pydantic stand-ins for models.schemas (a MagicMock on the dev host / under
# the stubbed conftests) only for the duration of the import and then restores
# the original models entries.  Without it this file cannot collect standalone
# and fails order-dependently once tests/services/conftest.py has run.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

code_sync = import_code_sync()

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


# ---------------------------------------------------------------------------
# #13851 — the excludes that stop a false drift signal deleting real files.
#
# A dry run of the autobot-backend resolve on a live, fully-synced host listed
# 55 deletions: 34 files under plugins/core-plugins (the entire plugin
# subsystem, deployed there by the `plugins` component) and the audit logs.
# Both were reported as drift only because the backend's walk cannot see who
# owns them, and neither exclude list covered them.
# ---------------------------------------------------------------------------


def test_protected_excludes_cover_logs() -> None:
    """logs/audit/*.jsonl was among the 55 dry-run deletions. No component in
    the repo tracks a logs/ directory, so this cannot hide a source file."""
    assert "logs" in _PROTECTED_EXCLUDES


def test_exclude_args_always_include_logs() -> None:
    assert "--exclude=logs" in _rsync_exclude_args([])


# The root conftest stubs `services.*` as MagicMocks, so the drift_checker
# lookups code_sync imports return empty here. These tests pin the WIRING — that
# whatever those functions return is anchored and scoped correctly. The values
# themselves are pinned against the real deployment map in
# services/drift_checker_test.py::TestForeignFilesAreNotDrift.
def _with_real_ownership(monkeypatch, owned: set[str], entries: set[str]) -> None:
    monkeypatch.setattr(code_sync, "owned_subtrees", lambda component: frozenset(owned))
    monkeypatch.setattr(code_sync, "deploy_only_entries", lambda component: frozenset(entries))


def test_backend_sync_excludes_the_plugins_subtree(monkeypatch) -> None:
    """plugins deploys INTO autobot-backend/plugins, so the backend's own
    delete-style sync would remove all 34 files. Anchored (`/plugins/`) so a
    nested directory of the same name elsewhere is untouched."""
    _with_real_ownership(monkeypatch, {"plugins"}, set())
    args = _rsync_exclude_args([], "autobot-backend")
    assert "--exclude=/plugins/" in args


def test_backend_sync_excludes_the_runtime_worker_registry(monkeypatch) -> None:
    """config/npu_workers.yaml is written by the running backend and has no
    counterpart in source — a delete-style sync would drop the registry.
    Excluded as a file (no trailing slash), unlike a subtree."""
    _with_real_ownership(monkeypatch, set(), {"config/npu_workers.yaml"})
    args = _rsync_exclude_args([], "autobot-backend")
    assert "--exclude=/config/npu_workers.yaml" in args


def test_component_omitted_keeps_previous_behaviour() -> None:
    """Callers that pass no component get exactly the pre-#13851 set plus
    logs — no anchored foreign excludes appear from nowhere."""
    args = _rsync_exclude_args([])
    assert not [a for a in args if a.startswith("--exclude=/")]
