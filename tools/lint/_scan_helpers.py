#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared helpers for this repository's regression-prevention hooks.

Home is ``tools/lint/``, but the vacuity rule below is repository-wide, so
``scripts/`` and ``pipeline-scripts/`` guards import it from here too rather
than each restating the floor.

Extracted per #5449 after #5394 + #5418 showed two hooks with byte-
identical ``_iter_target_files`` implementations drifted independently
(``.worktrees`` exclusion fixed in one, then the other). A single source
of truth prevents a third such drift.

VACUITY (#14896)
----------------
A sweep that reaches zero files reports "clean" and exits 0 — the same
answer a genuinely clean tree gives, with none of the evidence. #14896
found the floor guarding that already existed on the ``--audit`` path of
two hooks and nowhere on the pre-commit path, so the eleven full-repo
consumers of :func:`iter_python_files` could each have lost their reach
silently.

Two pieces close it, and the split between them is the whole design:

* :func:`tracked_paths` **raises** rather than returning ``[]``. An
  enumeration that failed and an empty repository are indistinguishable
  downstream, so the distinction is made here, where the return code is
  still visible.
* :func:`enforce_reach` applies a floor **in full-repo mode only**.
  pre-commit hands a hook the changed files and nothing else: a PR that
  touched no Python legitimately gives that hook zero files, and a floor
  applied there would redden every such PR in the repository. The
  exemplar is ``check_git_toplevel_env_scrubbed.main``, which has taken
  this shape since #15176.
"""

from __future__ import annotations

import logging
import posixpath
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from autobot_shared.paths import scrubbed_git_env  # noqa: E402

# Plain stdlib logging, deliberately (#1082): these helpers run inside bare
# pre-commit hook scripts, and `autobot_shared.logging_manager` would drag
# config loading onto every commit. Same trade as
# `scripts/check_python_file_size.py`.
logger = logging.getLogger(__name__)

# Directories skipped during full-repo scans. Kept as a frozenset so hooks
# can reference the same constant without risk of per-hook mutation. Adding
# a new entry here covers all current + future callers in one place.
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".git",
        "dist",
        "build",
        ".worktrees",  # parallel-work git worktrees (#5394, #5418)
    }
)

#: Floor for a full-repo ``*.py`` sweep. 5,319 files were tracked when this
#: landed, so this sits ~25% below the real count: low enough that ordinary
#: churn (or a subtree moving out) never trips it, high enough that a sweep
#: which lost its reach — wrong root, wrong CWD, a filter inverted — cannot
#: land under it and still look clean.
PY_FLOOR = 4000


def _looks_like_a_pattern(entry: str) -> bool:
    """Whether *entry* is already a pathspec rather than a bare directory name."""
    return any(ch in entry for ch in "*?[") or "/" in entry


class EmptyEnumeration(RuntimeError):
    """`git ls-files` succeeded and listed nothing.

    A subclass so every existing `except RuntimeError` keeps working, while a
    caller that has its OWN floor can tell this apart from a git failure. Those
    are different conditions and want different answers: a broken git is an
    error, an empty result is a finding the caller may be contracted to report
    in its own words (#15962).
    """


def tracked_paths(repo_root: Path, *patterns: str, exclude: Sequence[str] = ()) -> List[str]:
    """Git-tracked paths under *repo_root* matching *patterns*, repo-relative.

    *exclude* entries become git ``:(exclude)`` pathspecs, so **git does the
    matching** (#15926). Every caller before this filtered in Python after
    enumerating, which is two matchers over one question — and #15510 is what
    that costs: an exclusion tested against the ABSOLUTE path fired on every
    file when the checkout itself lived under a directory of that name. Git
    matches the same repo-relative path it returns, so the two cannot disagree.

    Pass bare directory or glob fragments (``"node_modules"``, ``"*.min.js"``);
    the ``:(exclude)`` prefix and the rooting are added here, so no caller
    re-decides the pathspec syntax. A bare entry needs no trailing ``/*``: git
    excludes a directory's contents from the bare name, measured identical for
    files, directories and nested directories (#16013).

    ``cwd=repo_root`` anchors the answer: run from a subdirectory,
    ``git ls-files`` still succeeds and returns paths re-prefixed relative
    to *that* directory, which is a confidently wrong result rather than an
    empty one. ``env=scrubbed_git_env()`` removes the ``GIT_DIR`` a hook
    exports, which would otherwise enumerate one checkout's index while
    *repo_root* names another (#15176).

    Raises:
        RuntimeError: git failed, or listed nothing. Returning ``[]`` here
            is how a broken enumeration reads as a clean tree downstream —
            the caller cannot tell the two apart, so this refuses to make
            them look alike.
    """
    # A directory name needs `/*` to exclude its contents; a pattern that already
    # contains a glob or a slash is passed through as the caller wrote it.
    # Two things have to be right here, and each was wrong on its own.
    #
    # 1. ROOTING. `git ls-files` derives a common prefix from the POSITIVE
    #    pathspecs and anchors traversal to it, so an unrooted exclude under a
    #    single prefixed positive matches every entry and empties the result:
    #
    #        scripts/*.py                 + :(exclude)*_test.py  ->  0 files
    #        scripts/*.py + tools/*.py    + :(exclude)*_test.py  ->  correct
    #
    #    Adding a second positive under a different top-level directory empties
    #    the common prefix and the identical exclude starts working. So an entry
    #    with no `/` is emitted once per distinct positive prefix (#16013).
    #
    # 2. FILE vs DIRECTORY needs no special case once (1) is right. A bare
    #    `:(exclude)scripts` already excludes everything under it, and
    #    `:(exclude)a.py` excludes the file — measured identical to emitting a
    #    `<entry>/*` companion for directories, files and nested directories.
    #    An earlier draft emitted both; the mutation that deleted the companion
    #    changed no result, which is what showed it was dead. `_looks_like_a_pattern`
    #    is retained for the callers that ask whether an entry IS a pattern.
    # `or [""]` because NO positive pattern means no prefix, not no exclusions.
    # Without it an empty `patterns` produced an empty prefix set, the loop below
    # emitted nothing, and `tracked_paths(root, exclude=["generated"])` returned
    # `generated` — an exclusion that silently does nothing, which is worse than
    # one that fails because the result comes back plausible and full-length.
    # `EmptyEnumeration` cannot catch it: the list is non-empty, just wrong.
    positive_prefixes = sorted({posixpath.dirname(p) for p in patterns}) or [""]
    excludes = []
    for entry in exclude:
        if "/" in entry:
            rooted = [entry]  # already rooted; re-prefixing would move it
        else:
            rooted = [posixpath.join(pre, entry) if pre else entry for pre in positive_prefixes]
        excludes.extend(f":(exclude){spec}" for spec in rooted)
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", *patterns, *excludes],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=scrubbed_git_env(),
    )
    described = " ".join(patterns) or "<all>"
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files {described} failed in {repo_root}: {result.stderr.strip()}")
    paths = [line.replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
    if not paths:
        raise EmptyEnumeration(
            f"git ls-files {described} listed nothing in {repo_root} — refusing to "
            "report an empty enumeration as a clean tree."
        )
    return paths


def enforce_reach(reached: int, floor: int, *, hook: str, full_repo: bool) -> int:
    """``1`` when a full-repo sweep landed under *floor*, else ``0``.

    **Full-repo mode only.** pre-commit passes the changed files as argv, and
    a PR touching nothing in a hook's scope legitimately gives it zero files;
    a floor applied there would fail every such PR in the repository. That is
    why *full_repo* is a keyword the caller must state rather than something
    inferred here.
    """
    if not full_repo or reached >= floor:
        return 0
    logger.error("[%s] full-repo sweep reached only %d file(s); floor is %d.", hook, reached, floor)
    logger.error("FIX THE SWEEP, not the tree — a clean result below this floor asserts nothing.")
    return 1


def scan_python_files(args: List[str], repo_root: Path) -> Tuple[List[Path], bool]:
    """``(files, full_repo)`` — :func:`iter_python_files` with the mode exposed.

    The mode is what :func:`enforce_reach` needs and what a bare generator
    cannot tell its caller, so every hook that wants a floor calls this
    instead of re-deriving ``not argv`` for itself.
    """
    return list(iter_python_files(args, repo_root)), not args


def iter_python_files(args: List[str], repo_root: Path) -> Iterable[Path]:
    """Yield target ``.py`` files for a lint hook.

    Two modes:

    * **Explicit argv** — pre-commit / CI passes changed file paths. Each
      is filtered by ``.py`` suffix and yielded as-is (absolute or
      repo-relative). Directory exclusions are NOT applied because
      explicit paths are trusted.
    * **Full-repo scan** — no argv (e.g. ``python3 tools/lint/hook.py``).
      Enumerates via :func:`tracked_paths` and skips any path whose parts
      intersect :data:`EXCLUDED_DIR_NAMES`.

    Full-repo enumeration is git-tracked rather than ``rglob``: a stray
    local file (a scratch script, an accidental venv the exclusions miss)
    cannot masquerade as a repo file, and an enumeration failure raises out
    of :func:`tracked_paths` instead of yielding nothing. Exclusions are
    matched against the **relative** path's parts — an absolute match would
    fire on any checkout living under a directory named ``build`` or
    ``.worktrees`` (#14484).

    Args:
        args: Positional argv tail (argv[1:]). When truthy, treated as
            explicit file list. When empty, triggers full-repo mode.
        repo_root: Repository root path, used to resolve relative argv
            entries and to anchor ``git ls-files``.

    Yields:
        ``Path`` objects for each target file.
    """
    if args:
        for a in args:
            p = Path(a)
            if not p.is_absolute():
                p = repo_root / p
            if p.is_file() and p.suffix == ".py":
                yield p
        return

    for rel in tracked_paths(repo_root, "*.py"):
        parts = Path(rel).parts
        if any(part in EXCLUDED_DIR_NAMES for part in parts):
            continue
        yield repo_root / rel
