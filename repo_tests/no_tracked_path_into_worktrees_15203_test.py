# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No tracked file builds a real path into the repo's own `.worktrees/` (#15203).

`advanced_rag_optimizer_rerank_test.py` defined:

    _WORKTREE = str(project_root() / ".worktrees" / "issue-2034" / "autobot-backend")

naming one developer's worktree for an issue closed long ago. It was referenced
nowhere in the file — a dead constant — so removal was the whole fix, and what
this guard protects is that it does not come back in a live form.

`.worktrees/` holds throwaway checkouts. A tracked file that resolves a path
inside one is depending on a directory that exists on one machine, for one
issue, until someone cleans up. It cannot fail on the machine that wrote it,
which is the shape of defect that survives review.

Two things are deliberately NOT flagged, because both are correct:

* a `tmp_path / ".worktrees"` fixture — that is a test constructing its own
  scratch tree, not reaching into the repo's
* a `.worktrees` entry in a skip/ignore list (e.g. `SKIP_DIRS`) — that is code
  *avoiding* the directory, which is the behaviour this guard wants
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: A path built under *this repo's* worktrees directory — the #15203 defect.
#:
#: Deliberately anchored on a repo-root accessor rather than on any string
#: containing `.worktrees`. Two things that string also appears in are correct:
#: skip-list entries (`"/.worktrees/"`), and synthetic fixture paths in tests
#: (a `Path(...)` built from an invented root), which construct a scenario
#: rather than reaching into the real tree. Both were false positives on the
#: first draft, and a guard that fires on correct code gets suppressed.
#:
#: NOT covered here: a hard-coded absolute path to a real machine's worktree.
#: That is a machine-specific-path defect rather than a worktree one, and it
#: belongs to whatever enforces the "no machine-specific absolute paths" rule.
_BUILDS_PATH = re.compile(
    r"""(?:project_root\(\)|REPO_ROOT|_REPO_ROOT|repo_root\(\))\s*/\s*["']\.worktrees["']"""
)

#: Constructing a scratch tree under pytest's tmp_path is not the repo's.
_SCRATCH = re.compile(r"tmp_path\s*/\s*[\"']\.worktrees[\"']")


def _tracked_python_files() -> List[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [REPO_ROOT / p for p in out]


#: This file quotes the defective line in its docstring and again in the
#: contrast cases below, so it matches its own pattern. It is excluded by path
#: rather than by making the pattern cleverer -- documenting what a guard
#: catches should not require writing it in a way the guard cannot see. It
#: became visible only after the first commit, because `git ls-files` does not
#: list an untracked file: the guard passed while the file was new and failed
#: the moment it was staged.
_SELF = Path(__file__).resolve()


def _offenders() -> List[Tuple[str, int, str]]:
    found: List[Tuple[str, int, str]] = []
    for path in _tracked_python_files():
        if path.resolve() == _SELF:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover - unreadable tracked file
            continue
        if ".worktrees" not in text:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if not _BUILDS_PATH.search(line) or _SCRATCH.search(line):
                continue
            found.append((str(path.relative_to(REPO_ROOT)), number, line.strip()))
    return found


_FILES = _tracked_python_files()


def test_the_sweep_reached_the_tree() -> None:
    """Guard the guard: an empty file list passes the assertion below vacuously."""
    assert len(_FILES) > 500, f"only {len(_FILES)} tracked .py files found — the sweep broke"


def test_no_tracked_file_builds_a_path_into_the_repos_worktrees() -> None:
    offenders = _offenders()

    assert not offenders, "tracked files resolving a path inside .worktrees/:\n" + "\n".join(
        f"  {name}:{number}: {line}" for name, number, line in offenders
    )


@pytest.mark.parametrize(
    "line,should_flag",
    [
        ('_W = str(project_root() / ".worktrees" / "issue-2034" / "backend")', True),
        ('_W = str(REPO_ROOT / ".worktrees" / "issue-9")', True),
        ('scratch = tmp_path / ".worktrees" / "fake"', False),
        ('SKIP_DIRS = ("venv/", "node_modules/", ".worktrees/")', False),
        ('# .worktrees holds throwaway checkouts', False),
        # Real skip-list entries this guard must not fire on — all three were
        # false positives on the first draft, which is why they are pinned.
        ('    "/.worktrees/",', False),
        ('SKIP = ("/.worktrees/", "/venv/")', False),
        # An invented root rather than a /home/... one: #13409 blocks developer
        # absolute paths in tracked source, and this fixture tripped it — a
        # contrast case must not itself be the thing another guard forbids.
        ('fake_root = Path("/srv/example/repo/.worktrees/issue-X")', False),
    ],
)
def test_the_matcher_separates_building_from_mentioning(line: str, should_flag: bool) -> None:
    """The contrast the guard depends on.

    Flagging every mention of `.worktrees` would hit the skip-lists that exist
    precisely to avoid it — a guard that fires on the correct behaviour gets
    suppressed, and then protects nothing.
    """
    flagged = bool(_BUILDS_PATH.search(line)) and not _SCRATCH.search(line)

    assert flagged is should_flag, f"matcher {'flagged' if flagged else 'missed'}: {line}"
