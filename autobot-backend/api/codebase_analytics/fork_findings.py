# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Symbol-fork clusters as codebase-analytics problems (#18067).

The CI ratchet ``tools/lint/check_symbol_forks.py`` and this module count with
ONE function, ``autobot_shared.symbol_forks.scan_symbol_forks``; there is no
second detector here. A test pins that the two counts agree on the real tree.

A pass that could not look says so (``ran=False`` with a ``reason``) instead of
returning zero clusters: "found no forks" and "read no files" are different
facts and the dashboard must not render the second as the first.
"""

from __future__ import annotations

import subprocess  # nosec B404  # only for its exception type
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.status_enums import Severity
from autobot_shared.symbol_forks import (
    FORK_EXCEPTIONS_RELPATH,
    FORK_ROOTS,
    ForkCluster,
    ForkScan,
    fork_apply_exceptions,
    fork_load_exceptions,
    scan_symbol_forks,
)

from .chromadb_storage import make_problem_dict

logger = get_logger(__name__)

SYMBOL_FORK_PROBLEM_TYPE = "code_smell_symbol_fork"


@dataclass
class ForkPassOutcome:
    """What the fork pass did: ran (with the reach it had) or did not."""

    ran: bool
    reason: str | None = None
    clusters: int = 0
    parsed: int = 0
    listed: int = 0
    problems: List[Dict[str, Any]] = field(default_factory=list)


def _roots_for(root: Path) -> tuple[str, ...]:
    """AutoBot's own roots when the source has them, else the whole tree.

    The population rules are the detector's either way; only the directories
    swept differ, because a source that is not AutoBot has none of the roots.
    """
    present = tuple(r for r in FORK_ROOTS if (root / r).is_dir())
    return present or (".",)


def fork_problem(cluster: ForkCluster) -> Dict[str, Any]:
    """One cluster as one problem row, anchored at its first definition."""
    first = cluster.definitions[0]
    where = ", ".join(f"{d.path}:{d.lineno}" for d in cluster.definitions[:5])
    more = len(cluster.definitions) - 5
    return make_problem_dict(
        problem_type=SYMBOL_FORK_PROBLEM_TYPE,
        severity=Severity.MEDIUM.value,
        file_path=first.path,
        line=first.lineno,
        description=(
            f"'{cluster.name}' is defined at module level in {len(cluster.definitions)} files"
            f"{' (bodies have drifted)' if cluster.drifted else ''}: {where}"
            f"{f' and {more} more' if more > 0 else ''}."
        ),
        suggestion="Merge the copies into one canonical definition, or give each its own concept name.",
        file_category="code",
    )


def outcome_from_scan(scan: ForkScan) -> ForkPassOutcome:
    """A finished sweep as an outcome; zero PARSED files is a failure to look."""
    if scan.parsed == 0:
        return ForkPassOutcome(
            ran=False,
            reason=f"parsed 0 of {scan.listed} listed python files; no claim is made about forks",
            listed=scan.listed,
        )
    ordered = sorted(scan.clusters.values(), key=lambda c: c.name)
    return ForkPassOutcome(
        ran=True,
        clusters=len(ordered),
        parsed=scan.parsed,
        listed=scan.listed,
        problems=[fork_problem(c) for c in ordered],
    )


def run_fork_pass(root_path: str) -> ForkPassOutcome:
    """Sweep ``root_path`` with the CI detector; never raises, never fakes a zero."""
    root = Path(root_path)
    try:
        scan = scan_symbol_forks(root, _roots_for(root))
        exceptions = fork_load_exceptions(root / FORK_EXCEPTIONS_RELPATH)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as exc:
        logger.warning("[#18067] Symbol-fork pass did not run for %s: %s", root_path, exc)
        return ForkPassOutcome(ran=False, reason=f"{type(exc).__name__}: {exc}")
    # The CI ratchet's recorded per-service exceptions (#18688), so both report the same clusters.
    scan.clusters, problems = fork_apply_exceptions(scan.clusters, exceptions)
    for problem in problems:
        logger.warning("[#18688] Symbol-fork exception record: %s", problem)
    return outcome_from_scan(scan)
