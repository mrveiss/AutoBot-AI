# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18954 — the deduplicated guards resolve their root and exclusions at call time.

Two behaviours the shared cores must keep, pinned so a refactor cannot drop them:

* the file-size and exclude-anchoring guards resolve the tree they walk through
  ``autobot_shared.paths.project_root()``, which honours ``AUTOBOT_PROJECT_ROOT``
  before anything inferred from the file's location (#18101, single resolver);
* ``tracked_*_files`` reads the script's ``EXCLUDED_PREFIXES`` when it is called,
  so the "live namespace" contract of ``tools/lint/_file_size_guard.py`` holds
  for the enumerator too -- a binding taken at import would ignore a patch.
"""

from __future__ import annotations

import importlib.util
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = repo_root()
_SIZE_SCRIPTS = {
    "python": ("check_python_file_size.py", "big.py", "tracked_python_files"),
    "frontend": ("check_frontend_file_size.py", "big.ts", "tracked_frontend_files"),
    "shell": ("check_shell_file_size.py", "big.sh", "tracked_shell_files"),
}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_repo(root: Path, files: dict[str, str]) -> Path:
    """A throwaway git checkout holding *files* (rel path -> text), all staged."""
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    for argv in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *argv], cwd=root, check=True, env=scrubbed_git_env())  # nosec B603 B607
    return root


@pytest.fixture(params=sorted(_SIZE_SCRIPTS))
def size_hook(request):
    script, big, tracked = _SIZE_SCRIPTS[request.param]
    return _load(REPO_ROOT / "scripts" / script, f"_{script[:-3]}_18954"), big, tracked


def test_size_audit_walks_the_tree_named_by_autobot_project_root(size_hook, tmp_path, monkeypatch):
    """The walk covers AUTOBOT_PROJECT_ROOT's tree, not the checkout the script lives in.

    Reverting ``repo_root`` to a path derived from ``__file__`` would walk the real repo:
    ``reached`` would be in the thousands and ``big.*`` would never be named.
    """
    hook, big, _ = size_hook
    tree = _git_repo(tmp_path / "tree", {big: "x\n" * (hook.MAX_LINES + 1), "ok.txt": "x\n"})
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", str(tree))
    reached, problems = hook.audit_ceilings()
    assert reached == 1
    assert any(p.startswith(f"{big}: {hook.MAX_LINES + 1} lines") for p in problems)


def test_size_root_is_the_checkout_when_the_variable_is_unset(size_hook, tmp_path, monkeypatch):
    """Contrast: unset, ``repo_root()`` is the real checkout, so the env var is what moved it above."""
    hook, big, _ = size_hook
    tree = _git_repo(tmp_path / "tree", {big: "x\n"})
    monkeypatch.delenv("AUTOBOT_PROJECT_ROOT", raising=False)
    assert hook.repo_root().resolve() != tree.resolve()
    assert (hook.repo_root() / "autobot_shared").is_dir()


def test_tracked_files_read_excluded_prefixes_at_call_time(size_hook, tmp_path, monkeypatch):
    """Patching EXCLUDED_PREFIXES reaches the enumerator; a partial bound at import would not."""
    hook, big, tracked = size_hook
    tree = _git_repo(tmp_path / "tree", {f"keep/{big}": "x\n", f"drop/{big}": "x\n"})
    enumerate_files = getattr(hook, tracked)
    monkeypatch.setattr(hook, "EXCLUDED_PREFIXES", ())
    assert sorted(enumerate_files(tree)) == [f"drop/{big}", f"keep/{big}"]
    monkeypatch.setattr(hook, "EXCLUDED_PREFIXES", ("drop/",))
    assert enumerate_files(tree) == [f"keep/{big}"]


def test_flake8_audit_reads_the_flake8_config_under_autobot_project_root(tmp_path, monkeypatch):
    checker = _load(REPO_ROOT / "tools" / "lint" / "check_flake8_exclude_anchoring.py", "_flake8_anchor_18954")
    tree = _git_repo(tmp_path / "tree", {".flake8": "[flake8]\nexclude = tests\n", "a/m.py": "x = 1\n"})
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", str(tree))
    reached, problems = checker.audit_excludes()
    assert reached == 1  # the temp .flake8 has one entry; the real one has dozens
    assert any("unanchored exclude entries ['tests']" in p for p in problems)


def test_bandit_audit_reads_the_bandit_config_under_autobot_project_root(tmp_path, monkeypatch):
    checker = _load(REPO_ROOT / "tools" / "lint" / "check_bandit_exclude_anchoring.py", "_bandit_anchor_18954")
    tree = _git_repo(tmp_path / "tree", {".bandit": "exclude_dirs:\n  - tests\n", "a/m.py": "x = 1\n"})
    monkeypatch.setenv("AUTOBOT_PROJECT_ROOT", str(tree))
    reached, problems = checker.audit_excludes()
    assert reached == 1
    assert any("unanchored exclude_dirs entries ['tests']" in p for p in problems)
