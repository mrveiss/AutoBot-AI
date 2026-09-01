# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-cross-gui-duplicate (#14907, #14908).

Two families:
  - direct unit tests against the module's collector functions (fast, no
    subprocess, no need to satisfy the real vacuity floors);
  - one end-to-end subprocess test proving the fail-closed vacuity floor
    fires on a too-small tree, and one proving a real violation blocks the
    process exit code — the artifact a caller actually invokes.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-cross-gui-duplicate"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("cross_gui_duplicate_guard", str(HOOK_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


guard = _load_module()


def _make_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    for app in guard.APPS:
        (tmp_path / app / "src" / "composables").mkdir(parents=True)
        (tmp_path / app / "src" / "utils").mkdir(parents=True)
        (tmp_path / app / "src" / "types").mkdir(parents=True)
    return tmp_path


def _write(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Composable filename collisions
# ---------------------------------------------------------------------------


def test_composable_collision_detected_when_not_a_kit_shim(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        _write(repo, f"{app}/src/composables/useDup.ts", "export function useDup() { return 1 }\n")

    violations, scanned = guard.collect_composable_violations(repo)

    assert scanned == 2
    assert len(violations) == 1
    assert "useDup.ts" in violations[0]


def test_composable_collision_passes_when_both_sides_are_kit_shims(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    shim = "export { useDup } from '@autobot/ui'\n"
    for app in guard.APPS:
        _write(repo, f"{app}/src/composables/useDup.ts", shim)

    violations, _scanned = guard.collect_composable_violations(repo)

    assert violations == []


def test_composable_collision_respects_filename_allowlist(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        _write(repo, f"{app}/src/composables/usePrometheusMetrics.ts", "export function x() {}\n")

    violations, _scanned = guard.collect_composable_violations(repo)

    assert violations == []


def test_composable_no_collision_when_only_one_side_has_the_file(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, f"{guard.APPS[0]}/src/composables/useOnlyMain.ts", "export function x() {}\n")

    violations, scanned = guard.collect_composable_violations(repo)

    assert violations == []
    assert scanned == 1


# ---------------------------------------------------------------------------
# Type-name collisions (utils/types, top-level only)
# ---------------------------------------------------------------------------


def test_type_name_collision_detected(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        _write(repo, f"{app}/src/utils/vocab.ts", "export type DupVocab = 'a' | 'b'\n")

    violations, scanned = guard.collect_type_violations(repo)

    assert scanned == 2
    assert any("DupVocab" in v for v in violations)


def test_type_name_reexport_is_not_a_declaration(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, f"{guard.APPS[0]}/src/utils/vocab.ts", "export type ReExported = 'a' | 'b'\n")
    _write(repo, f"{guard.APPS[1]}/src/utils/vocab.ts", "export type { ReExported } from '@autobot/ui'\n")

    violations, _scanned = guard.collect_type_violations(repo)

    assert violations == []


def test_type_name_collision_respects_allowlist(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        _write(repo, f"{app}/src/types/health.ts", "export type HealthStatus = 'ok' | 'down'\n")

    violations, _scanned = guard.collect_type_violations(repo)

    assert violations == []


def test_type_name_scan_ignores_nested_directories(tmp_path: Path) -> None:
    """The scope is deliberately top-level utils/types, not recursive (avoids
    generated OpenAPI-contract false positives — see the hook's own header
    comment and #15401)."""
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        _write(repo, f"{app}/src/types/generated/api.ts", "export type paths = {}\n")

    violations, scanned = guard.collect_type_violations(repo)

    assert violations == []
    assert scanned == 0


def test_type_violations_collect_all_not_just_first(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        _write(repo, f"{app}/src/utils/a.ts", "export type DupA = 'x'\n")
        _write(repo, f"{app}/src/utils/b.ts", "export type DupB = 'y'\n")

    violations, _scanned = guard.collect_type_violations(repo)

    names_flagged = {n for v in violations for n in ("DupA", "DupB") if n in v}
    assert names_flagged == {"DupA", "DupB"}


# ---------------------------------------------------------------------------
# End-to-end: the artifact actually invoked by pre-commit
# ---------------------------------------------------------------------------


def _run_hook(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_vacuity_floor_fails_closed_on_a_too_small_tree(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "FATAL" in result.stdout + result.stderr


def test_end_to_end_blocks_on_real_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    # Satisfy the vacuity floor with cheap filler files, then add one real
    # cross-GUI composable fork.
    for app in guard.APPS:
        for i in range(guard.MIN_COMPOSABLE_FILES_SCANNED):
            _write(repo, f"{app}/src/composables/useFiller{i}.ts", "export function f() {}\n")
        for i in range(guard.MIN_VOCAB_FILES_SCANNED):
            _write(repo, f"{app}/src/utils/filler{i}.ts", "export const x = 1\n")
        _write(repo, f"{app}/src/composables/useForked.ts", "export function useForked() { return 1 }\n")

    result = _run_hook(repo)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "useForked.ts" in result.stdout


def test_hook_script_exists_and_is_executable() -> None:
    """core.fileMode=false hides a missing +x bit on a local clone until a
    fresh CI checkout sets working-tree perms from git's tracked mode
    (#14162's pattern, applied to this hook)."""
    assert os.access(HOOK_PATH, os.X_OK), f"{HOOK_PATH} is not executable on disk"
