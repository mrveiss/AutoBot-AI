# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The symbol-fork roots reach the workers, infrastructure and script trees (#18559, #17312).

``FORK_ROOTS`` covered only the two backends and ``autobot_shared``, so a function copied from
the backend into a worker, a script or the infrastructure tree was invisible to the ratchet.
Each case plants a copy of a REAL backend function (read from the tree, not hand-typed) into
one of the added roots, in a throwaway git repo, and asks the detector's own enumeration and
clustering to find it. The control plants the same copy under a root that is not declared and
must see nothing, so a pass cannot mean "the detector flags everything".
"""

from __future__ import annotations

import ast
import subprocess  # nosec B404  # git plumbing in a throwaway repo, fixed argv, no shell
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.isolated_git import isolated_git_env
from autobot_shared.symbol_forks import FORK_ROOTS, fork_find_clusters, fork_tracked_python_files

ADDED_ROOTS = (
    "autobot-npu-worker",
    "autobot-tts-worker",
    "autobot-browser-worker",
    "autobot-infrastructure",
    "scripts",
    "tools",
    "pipeline-scripts",
)
_SOURCE = "autobot-backend/utils/chat_utils.py"
_FUNCTION = "generate_message_id"


def _backend_function_source() -> str:
    text = (repo_root() / _SOURCE).read_text(encoding="utf-8")
    for node in ast.parse(text).body:
        if isinstance(node, ast.FunctionDef) and node.name == _FUNCTION:
            segment = ast.get_source_segment(text, node)
            assert segment, f"{_FUNCTION} has no source segment in {_SOURCE}"
            return segment + "\n"
    raise AssertionError(f"{_FUNCTION} is gone from {_SOURCE}; point this control at another backend function")


def _git(cwd: Path, *argv: str) -> None:
    subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", *argv], cwd=cwd, env=isolated_git_env(), check=True, capture_output=True, timeout=60
    )


def _clusters_with_planted_copy(tmp_path: Path, root: str):
    body = _backend_function_source()
    for rel in (_SOURCE, f"{root}/planted_copy.py"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    return fork_find_clusters(fork_tracked_python_files(tmp_path), tmp_path).clusters


def test_every_added_root_is_declared() -> None:
    assert set(ADDED_ROOTS) <= set(FORK_ROOTS), sorted(set(ADDED_ROOTS) - set(FORK_ROOTS))


@pytest.mark.parametrize("root", ADDED_ROOTS)
def test_a_backend_function_copied_into_an_added_root_is_caught(tmp_path: Path, root: str) -> None:
    clusters = _clusters_with_planted_copy(tmp_path, root)
    assert _FUNCTION in clusters, f"a copy of {_FUNCTION} planted under {root}/ was not clustered"
    paths = {d.path for d in clusters[_FUNCTION].definitions}
    assert paths == {_SOURCE, f"{root}/planted_copy.py"}


def test_the_same_copy_under_an_undeclared_root_is_not_seen(tmp_path: Path) -> None:
    """Contrast: the pass above is the root's doing, not a detector that flags every copy."""
    body = _backend_function_source()
    for rel in (_SOURCE, "undeclared-root/planted_copy.py"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    listed = fork_tracked_python_files(tmp_path)
    assert all(not str(p).startswith("undeclared-root/") for p in listed)
    assert _FUNCTION not in fork_find_clusters(listed, tmp_path).clusters
