#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One run-loop for the repository's checkers (#14896).

Checkers each re-derived the same four things: where the repository root is,
how to enumerate tracked files, what a scan that reached nothing means, and
what exit code says so. The answers drifted (#14896 lists the drift).  This
module is the single answer.

EXIT CONTRACT
-------------
``0`` clean, ``1`` findings, ``2`` the scan is vacuous -- the root is not a git
toplevel, git is unavailable, the enumeration was empty, or a full-repo sweep
reached fewer files than its floor.  ``2`` is distinct from ``1`` on purpose: a
broken sweep and a dirty tree call for different people to act.

Works whether imported bare (``sys.path`` holds ``tools/lint``) or as
``tools.lint._check_harness``; the bootstrap mirrors ``_scan_helpers``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import EmptyEnumeration, GitEnumerationFailed, configure_logging, enforce_reach  # noqa: E402

from autobot_shared.paths import (  # noqa: E402
    GitRepoRootUnavailable,
    git_repo_root,
)

EXIT_CLEAN, EXIT_FOUND, EXIT_VACUOUS = 0, 1, 2

#: Whether the process cwd's git toplevel must equal the checker's root.
#: A decision is pending (#14896); the policy lives in :func:`cwd_policy_ok`
#: alone so changing it is a one-line edit. Off: the root is always taken from
#: the checker's own file, never from where it was launched.
REQUIRE_CWD_AT_ROOT = False

Scan = Callable[[List[str], Path], Tuple[int, List[str]]]


class VacuousScan(RuntimeError):
    """The scan could not have found anything, so its silence means nothing."""


def format_finding(path: object, line: object, msg: str) -> str:
    """``path:line: msg`` -- the shape every checker prints a finding in."""
    return f"{path}:{line}: {msg}"


def cwd_policy_ok(root: Path) -> bool:
    """Whether the launch directory is acceptable for *root* (see the constant)."""
    if not REQUIRE_CWD_AT_ROOT:
        return True
    return git_repo_root().resolve() == root.resolve()


def resolve_root(file_anchor: Path) -> Path:
    """The git toplevel two levels above *file_anchor*, or :class:`VacuousScan`."""
    root = Path(file_anchor).resolve().parents[2]
    try:
        top = git_repo_root(root)
    except GitRepoRootUnavailable as exc:
        raise VacuousScan(f"{root} is not a usable git checkout: {exc}") from exc
    if top.resolve() != root:
        raise VacuousScan(f"{root} is not a git toplevel (git says {top})")
    if not cwd_policy_ok(root):
        raise VacuousScan(f"the working directory is not inside {root}")
    return root


def _vacuous(log: logging.Logger, name: str, why: str) -> int:
    log.error("[%s] %s -- refusing to report a result for a scan that proved nothing.", name, why)
    return EXIT_VACUOUS


def _verdict(
    log: logging.Logger,
    name: str,
    reached: int,
    findings: List[str],
    *,
    full_repo: bool,
    floor: int,
    summary: Callable[[int], str] | None,
    unit: str,
) -> int:
    """Map a completed scan to ``0``/``1``/``2``: floor, nothing-reached, then findings."""
    if enforce_reach(reached, floor, hook=name, full_repo=full_repo, unit=unit):
        return EXIT_VACUOUS
    if full_repo and reached == 0:
        return _vacuous(log, name, f"nothing was scanned (0 {unit} reached in a full-repo sweep)")
    for finding in findings:
        log.error("%s", finding)
    if findings and summary is not None:
        log.error("%s", summary(len(findings)))
    return EXIT_FOUND if findings else EXIT_CLEAN


def run_check(
    name: str,
    scan: Scan,
    argv: Sequence[str],
    *,
    root: Path,
    floor: int = 0,
    logger: logging.Logger | None = None,
    summary: Callable[[int], str] | None = None,
    full_repo_of: Callable[[Sequence[str]], bool] | None = None,
    unit: str = "file(s)",
) -> int:
    """Run ``scan(argv, root) -> (reached, findings)`` and map it to ``0``/``1``/``2``.

    *argv* is the tail after the program name; empty means a full-repo sweep,
    the only mode a *floor* or the nothing-reached rule applies to (pre-commit
    legitimately hands a checker zero files). *summary*, when given, is logged
    after the findings with their count. Only the named vacuity errors become
    ``2``; any other exception is a checker bug and propagates with its traceback.

    A checker that takes flags as well as files passes *full_repo_of*, which maps
    *argv* to "this is a whole-repo sweep" from the parsed file list; the default
    reads a bare ``not argv``, which would count ``--flag`` alone as a scoped run.
    """
    log = logger or logging.getLogger(name)
    configure_logging(log)
    try:
        reached, findings = scan(list(argv), root)
    except (VacuousScan, EmptyEnumeration, GitEnumerationFailed, GitRepoRootUnavailable) as exc:
        return _vacuous(log, name, f"scan failed: {exc}")
    return _verdict(
        log,
        name,
        reached,
        findings,
        full_repo=(full_repo_of(argv) if full_repo_of else not argv),
        floor=floor,
        summary=summary,
        unit=unit,
    )


def run_anchored(
    name: str,
    scan: Scan,
    argv: Sequence[str],
    *,
    anchor: Path,
    floor: int = 0,
    logger: logging.Logger | None = None,
    summary: Callable[[int], str] | None = None,
    full_repo_of: Callable[[Sequence[str]], bool] | None = None,
    unit: str = "file(s)",
) -> int:
    """:func:`run_check` with the root resolved from *anchor* by :func:`resolve_root`.

    A root that is not a git toplevel is the same vacuity as an empty scan, so
    it exits ``2`` here rather than raising out of the checker's ``main``.
    """
    log = logger or logging.getLogger(name)
    configure_logging(log)
    try:
        root = resolve_root(anchor)
    except VacuousScan as exc:
        return _vacuous(log, name, f"cannot anchor the scan: {exc}")
    return run_check(
        name, scan, argv, root=root, floor=floor, logger=log, summary=summary, full_repo_of=full_repo_of, unit=unit
    )
