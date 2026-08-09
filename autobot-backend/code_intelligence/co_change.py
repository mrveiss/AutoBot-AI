# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Co-change coupling from git history (#13639).

Two files that keep changing in the same commit depend on each other in a way no
AST can see: a serialiser and its schema, a migration and the model it migrates, a
config key and the code that reads it. The call graph records the dependencies the
code *states*; this records the ones its history *demonstrates*.

The strength formula is normalised deliberately:

    strength(A, B) = co_changes(A, B) / max(changes(A), changes(B))

Dividing by the *larger* of the two change counts is what stops a
frequently-touched file — a router, a settings module, a changelog — from reading
as coupled to everything it ever appeared beside. Under a raw count, or under a
denominator of `min()`, such a file dominates every pair it takes part in. Here a
file that changes 500 times and co-changes 10 times with a rarely-touched one
scores 0.02, which is what it deserves.
"""

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, Iterable, List, Tuple

from autobot_shared.env_utils import env_float, env_int
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# How many commits must share two files before the pair is reported at all. One
# shared commit is a coincidence; the threshold is what separates a signal from a
# single tangled merge.
MIN_CO_CHANGES: int = env_int("AUTOBOT_COCHANGE_MIN_CO_CHANGES", default=3)

# Minimum normalised strength to report. Independent of the count above: a pair can
# clear the count and still be weak if either file changes constantly.
COCHANGE_STRENGTH_THRESHOLD: float = env_float("AUTOBOT_COCHANGE_STRENGTH_THRESHOLD", default=0.3)

# Default analysis window. Coupling decays — a pair that co-changed for a month two
# years ago is history, not structure.
COCHANGE_WINDOW_DAYS: int = env_int("AUTOBOT_COCHANGE_WINDOW_DAYS", default=180)


@dataclass(frozen=True)
class CoChangePair:
    """One coupled pair, carrying what produced the number."""

    source: str
    target: str
    co_changes: int
    source_changes: int
    target_changes: int
    strength: float

    def as_edge(self) -> Dict[str, object]:
        """Shape for persistence beside the graph's ``calls`` edges — never merged into them.

        A ``co_change`` edge is evidence of a different kind: it says two files
        moved together, not that one invokes the other. Folding them into one edge
        kind would make "who calls X" unanswerable.
        """
        return {
            "kind": "co_change",
            "source": self.source,
            "target": self.target,
            "co_changes": self.co_changes,
            "strength": round(self.strength, 4),
        }


class CoChangeAnalyzer:
    """Computes co-change coupling over a set of per-commit file sets.

    Takes the file sets rather than a repo so the analysis is testable without
    git, and so the expensive history walk stays an explicit, separate step —
    never something a request path triggers implicitly.
    """

    def __init__(
        self,
        min_co_changes: int = MIN_CO_CHANGES,
        strength_threshold: float = COCHANGE_STRENGTH_THRESHOLD,
    ) -> None:
        self.min_co_changes = min_co_changes
        self.strength_threshold = strength_threshold

    def analyze(self, commit_file_sets: Iterable[Iterable[str]]) -> List[CoChangePair]:
        """Return the coupled pairs, strongest first."""
        changes: Dict[str, int] = {}
        co_changes: Dict[Tuple[str, str], int] = {}

        for files in commit_file_sets:
            unique = sorted(set(files))
            for path in unique:
                changes[path] = changes.get(path, 0) + 1
            for pair in combinations(unique, 2):
                co_changes[pair] = co_changes.get(pair, 0) + 1

        pairs = [
            pair
            for (source, target), count in co_changes.items()
            if count >= self.min_co_changes
            and (pair := self._build(source, target, count, changes)).strength >= self.strength_threshold
        ]
        return sorted(pairs, key=lambda p: (-p.strength, -p.co_changes, p.source, p.target))

    @staticmethod
    def _build(source: str, target: str, count: int, changes: Dict[str, int]) -> CoChangePair:
        source_changes = changes.get(source, 0)
        target_changes = changes.get(target, 0)
        denominator = max(source_changes, target_changes)
        return CoChangePair(
            source=source,
            target=target,
            co_changes=count,
            source_changes=source_changes,
            target_changes=target_changes,
            strength=count / denominator if denominator else 0.0,
        )

    def coupled_with(self, path: str, pairs: Iterable[CoChangePair], limit: int = 10) -> List[CoChangePair]:
        """The strongest pairs involving *path*, in the order a reader wants them."""
        involved = [p for p in pairs if path in (p.source, p.target)]
        return sorted(involved, key=lambda p: (-p.strength, -p.co_changes))[:limit]
