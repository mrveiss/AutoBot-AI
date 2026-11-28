# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How many declared problem types actually emitted a row (#18067).

"18,200 problems across 26 types and none is a duplication finding" read as a
clean bill of health because nothing said which DECLARED types were silent. This
module states it as numbers: given the per-type counts a run produced, how many
types emitted, how many declared ones emitted nothing, and how many emitted
without being declared at all.

Declared = every ``AntiPatternType`` member (emitted as ``code_smell_<value>``)
plus the symbol-fork type. Legacy-alias members are included on purpose: the
per-file path still emits them (``duplicate_abstraction``, ``data_clumps``), and
leaving them out would report a type that emits rows as "undeclared".
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, FrozenSet, Mapping

from .fork_findings import SYMBOL_FORK_PROBLEM_TYPE

CODE_SMELL_PREFIX = "code_smell_"


@dataclass(frozen=True)
class TypeCoverage:
    """Counts of problem types by whether they were declared and whether they emitted."""

    declared: int
    declared_emitted: int
    emitted_nonzero: int
    declared_silent: tuple[str, ...]
    emitted_undeclared: tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["declared_silent_count"] = len(self.declared_silent)
        out["emitted_undeclared_count"] = len(self.emitted_undeclared)
        return out


def declared_problem_types() -> FrozenSet[str]:
    """Every declared type, spelled as it appears in stored rows."""
    from code_analysis.src.anti_pattern_detector import AntiPatternType

    return frozenset(f"{CODE_SMELL_PREFIX}{m.value}" for m in AntiPatternType) | {SYMBOL_FORK_PROBLEM_TYPE}


def problem_type_coverage(counts: Mapping[str, int]) -> TypeCoverage:
    """Coverage of the declared types by ``counts`` (problem type -> rows)."""
    declared = declared_problem_types()
    emitted = {t for t, n in counts.items() if n > 0}
    return TypeCoverage(
        declared=len(declared),
        declared_emitted=len(declared & emitted),
        emitted_nonzero=len(emitted),
        declared_silent=tuple(sorted(declared - emitted)),
        emitted_undeclared=tuple(sorted(emitted - declared)),
    )
