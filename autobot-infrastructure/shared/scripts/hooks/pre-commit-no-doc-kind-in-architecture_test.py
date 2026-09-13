# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for pre-commit-no-doc-kind-in-architecture (#15190, #15192, #15206).

Covers: the reach floor fails loudly on a too-small docs/architecture/ (rather
than silently reporting clean), a staged *_ANALYSIS.md/*_DESIGN.md/*_IMPLEMENTATION_PLAN.md
is blocked once the floor is met, and an ordinary architecture document is allowed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

HOOK_PATH = Path(__file__).resolve().parent / "pre-commit-no-doc-kind-in-architecture"
REACH_FLOOR = 50


def _test_git_env() -> dict[str, str]:
    return {**scrubbed_git_env(), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True, env=_test_git_env())


def _init_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    return tmp_path


def _seed_baseline_architecture_docs(repo: Path, count: int = REACH_FLOOR) -> None:
    arch = repo / "docs" / "architecture"
    arch.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (arch / f"STRUCTURAL_DOC_{i}.md").write_text(f"# Structural Doc {i}\n", encoding="utf-8")
    _git(repo, "add", "docs/architecture")
    _git(repo, "commit", "--quiet", "-m", "seed baseline architecture docs")


def _run_hook(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(HOOK_PATH)], cwd=repo, capture_output=True, text=True, env=_test_git_env())


def test_reach_floor_fails_loudly_on_small_architecture_dir(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_baseline_architecture_docs(repo, count=3)
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "FATAL" in (result.stdout + result.stderr)


def test_blocks_new_analysis_doc_in_architecture(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_baseline_architecture_docs(repo)
    f = repo / "docs" / "architecture" / "SOMETHING_NEW_ANALYSIS.md"
    f.write_text("# Something New Analysis\n", encoding="utf-8")
    _git(repo, "add", "docs/architecture/SOMETHING_NEW_ANALYSIS.md")
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "ANALYSIS" in (result.stdout + result.stderr)


def test_blocks_new_design_doc_in_architecture(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_baseline_architecture_docs(repo)
    f = repo / "docs" / "architecture" / "SOMETHING_NEW_DESIGN.md"
    f.write_text("# Something New Design\n", encoding="utf-8")
    _git(repo, "add", "docs/architecture/SOMETHING_NEW_DESIGN.md")
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout + result.stderr


def test_blocks_new_implementation_plan_doc_in_architecture(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_baseline_architecture_docs(repo)
    f = repo / "docs" / "architecture" / "SOMETHING_NEW_IMPLEMENTATION_PLAN.md"
    f.write_text("# Something New Implementation Plan\n", encoding="utf-8")
    _git(repo, "add", "docs/architecture/SOMETHING_NEW_IMPLEMENTATION_PLAN.md")
    result = _run_hook(repo)
    assert result.returncode != 0, result.stdout + result.stderr


def test_allows_ordinary_architecture_doc(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _seed_baseline_architecture_docs(repo)
    f = repo / "docs" / "architecture" / "NEW_SUBSYSTEM_ARCHITECTURE.md"
    f.write_text("# New Subsystem Architecture\n", encoding="utf-8")
    _git(repo, "add", "docs/architecture/NEW_SUBSYSTEM_ARCHITECTURE.md")
    result = _run_hook(repo)
    assert result.returncode == 0, result.stdout + result.stderr
