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
    _write(tmp_path, f"{guard.KIT_COMPONENTS_DIR}/SkipLink.vue", "<template><a /></template>\n")
    return tmp_path


def _write(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


_FORK_SFC = "<script setup lang=\"ts\">\nconst x = 1\n</script>\n<template><a>{{ x }}</a></template>\n"
_WRAPPER_SFC = (
    "<script setup lang=\"ts\">\nimport { SkipLink } from '@autobot/ui'\n</script>\n"
    "<template><SkipLink /></template>\n"
)
SLM_SKIP = "autobot-slm-frontend/src/components/common/SkipLink.vue"


@pytest.fixture
def no_grandfather(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard, "KIT_FORK_GRANDFATHER", {})


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


def test_composable_collision_respects_filename_allowlist(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setattr(guard, "FILENAME_ALLOWLIST", {"useTracked.ts"})
    for app in guard.APPS:
        _write(repo, f"{app}/src/composables/useTracked.ts", "export function x() {}\n")

    violations, _scanned = guard.collect_composable_violations(repo)

    assert violations == []


def test_the_former_prometheus_collision_is_no_longer_allowed(tmp_path: Path) -> None:
    """#18225: a usePrometheusMetrics.ts in both apps again is a violation."""
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        _write(repo, f"{app}/src/composables/usePrometheusMetrics.ts", "export function x() {}\n")

    violations, _scanned = guard.collect_composable_violations(repo)

    assert violations
    assert all("usePrometheusMetrics.ts" in str(v) for v in violations), violations


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
    # A name still on TYPE_NAME_ALLOWLIST. This used HealthStatus until #15401
    # and FormatBytesOptions until #19671 took each off the list; read the name
    # from the allowlist so the example cannot go stale again.
    name = sorted(guard.TYPE_NAME_ALLOWLIST)[0]
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        _write(repo, f"{app}/src/types/format.ts", f"export type {name} = {{ unit?: string }}\n")

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


# ---------------------------------------------------------------------------
# Kit component forks (#14776)
# ---------------------------------------------------------------------------


def test_kit_component_list_is_derived_and_non_empty_on_the_real_tree() -> None:
    """Control: the real kit yields names, incl. every grandfathered fork's kit twin."""
    repo_root = Path(__file__).resolve().parents[4]
    names = guard.kit_component_names(repo_root)
    assert names, "derived kit list is empty - the guard would pass vacuously"
    assert set(guard.KIT_FORK_GRANDFATHER) <= names


def test_kit_fork_detected(tmp_path: Path, no_grandfather: None) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, SLM_SKIP, _FORK_SFC)
    violations = guard.collect_kit_fork_violations(repo)
    assert len(violations) == 1 and "SkipLink.vue" in violations[0]


def test_kit_wrapper_passes(tmp_path: Path, no_grandfather: None) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, SLM_SKIP, _WRAPPER_SFC)
    assert guard.collect_kit_fork_violations(repo) == []


def test_importing_something_else_from_the_kit_is_still_a_fork(tmp_path: Path, no_grandfather: None) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, SLM_SKIP, "<script setup>\nimport { BaseModal } from '@autobot/ui'\n</script>\n")
    assert len(guard.collect_kit_fork_violations(repo)) == 1


def test_non_kit_basename_is_ignored(tmp_path: Path, no_grandfather: None) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, "autobot-frontend/src/components/Unrelated.vue", _FORK_SFC)
    assert guard.collect_kit_fork_violations(repo) == []


def test_kit_list_follows_the_kit_directory(tmp_path: Path, no_grandfather: None) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, f"{guard.KIT_COMPONENTS_DIR}/BaseNew.vue", "<template><i /></template>\n")
    _write(repo, "autobot-frontend/src/components/BaseNew.vue", _FORK_SFC)
    assert any("BaseNew.vue" in v for v in guard.collect_kit_fork_violations(repo))


def test_grandfathered_fork_passes_while_it_still_forks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, SLM_SKIP, _FORK_SFC)
    monkeypatch.setattr(guard, "KIT_FORK_GRANDFATHER", {"SkipLink": SLM_SKIP})
    assert guard.collect_kit_fork_violations(repo) == []


def test_grandfather_entry_that_became_a_wrapper_is_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, SLM_SKIP, _WRAPPER_SFC)
    monkeypatch.setattr(guard, "KIT_FORK_GRANDFATHER", {"SkipLink": SLM_SKIP})
    violations = guard.collect_kit_fork_violations(repo)
    assert len(violations) == 1 and "stale grandfather entry" in violations[0]


def test_grandfather_entry_for_a_missing_file_is_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    monkeypatch.setattr(guard, "KIT_FORK_GRANDFATHER", {"SkipLink": SLM_SKIP})
    assert "stale grandfather entry" in guard.collect_kit_fork_violations(repo)[0]


def test_grandfather_is_per_path_not_per_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    _write(repo, SLM_SKIP, _FORK_SFC)
    _write(repo, "autobot-frontend/src/components/SkipLink.vue", _FORK_SFC)
    monkeypatch.setattr(guard, "KIT_FORK_GRANDFATHER", {"SkipLink": SLM_SKIP})
    violations = guard.collect_kit_fork_violations(repo)
    assert len(violations) == 1 and "autobot-frontend/src/components/SkipLink.vue" in violations[0]


def test_vacuity_fails_closed_when_the_kit_list_is_empty() -> None:
    assert guard._check_vacuity(10**6, 10**6, 0) == 1


def test_end_to_end_blocks_on_kit_fork(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _make_repo(tmp_path)
    for app in guard.APPS:
        for i in range(guard.MIN_COMPOSABLE_FILES_SCANNED):
            _write(repo, f"{app}/src/composables/useFiller{i}.ts", "export function f() {}\n")
        for i in range(guard.MIN_VOCAB_FILES_SCANNED):
            _write(repo, f"{app}/src/utils/filler{i}.ts", "export const x = 1\n")
    _write(repo, SLM_SKIP, _FORK_SFC)
    result = _run_hook(repo)
    assert result.returncode != 0 and "SkipLink.vue" in result.stdout


def test_real_tree_is_clean_with_the_grandfather_list() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    assert guard.collect_kit_fork_violations(repo_root) == []


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


def test_real_tree_has_no_kit_fork_and_an_empty_grandfather_list() -> None:
    """M3.3 exit (#14776): every kit-named SFC in both apps is a wrapper over @autobot/ui."""
    repo_root = Path(__file__).resolve().parents[4]
    assert guard.KIT_FORK_GRANDFATHER == {}
    assert guard.collect_kit_fork_violations(repo_root) == []
