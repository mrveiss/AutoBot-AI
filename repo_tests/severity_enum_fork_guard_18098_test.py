#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18098 — one severity ladder, found by MEMBER SET rather than by name.

Sixteen `*Severity(Enum)` classes existed beside the canonical
`autobot_shared.status_enums.Severity`, ten of them exact subsets of it. Nothing could
see them:

* `tools/lint/check_symbol_forks.py` matches by **name**, so a fork under a fresh name
  produces no cluster at all.
* The #6973 pre-commit hook matches the literal token `Status`
  (`/^class[[:space:]]+[A-Za-z_]+Status[[:space:]]*\\([^)]*Enum[^)]*\\)/`); `grep -ci
  severity` on that hook returns 0.
* `repo_tests/enum_union_guard_test.py` pins the canonical's members and the string
  literals, and checks exactly two alias bindings by hardcoded path. None of that
  notices a rival class.

So this guard probes the member set, the way
`enum_union_guard_test.py::test_no_second_command_risk_enum_has_regrown` does for
`CommandRisk`. That immediately found `OptimizationPriority`, which every name-based
sweep had missed because its name says "priority".

Separate file rather than appended to `enum_union_guard_test.py`: that file is
grandfathered at 801 lines and a grandfathered file may not grow. Same reason
`enum_union_guard_severity_literal_shapes_test.py` is its own file, and like it this one
re-derives its scan instead of importing one.
"""

from __future__ import annotations

import ast
import functools

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

#: The five rungs every exact-subset fork carried.
SEVERITY_SUBSET_PROBE = frozenset({"INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"})

#: Scanned roots. `autobot-slm-backend/` is deliberately outside: its two severity
#: enums (`EventSeverity`, `SecurityEventSeverity`) are `(str, Enum)` persisted to
#: indexed `String(16)` columns, so neither is a drop-in alias and both are tracked on
#: the issue instead. Recorded in a test below so "green" is never read as "clean".
SCANNED_ROOTS = ("autobot-backend", "autobot_shared")

#: Exact subsets that are NOT aliased, because something builds an API or report dict
#: key set by ITERATING their members. The sites, by file and the enum each iterates --
#: deliberately not by line, per #15877:
#:
#:   api/code_intelligence.py        `for sev in OptimizationSeverity` (twice),
#:                                   `for sev in SecuritySeverity`,
#:                                   `for sev in PerformanceSeverity`
#:   code_intelligence/testing_pattern_analyzer.py   `for s in TestPatternSeverity`
#:   code_intelligence/llm_pattern_analyzer.py       `for priority in OptimizationPriority`
#:
#: Aliasing these to the ten-rung canonical grows those responses from five keys to ten,
#: against a frontend type that is deliberately the narrow five --
#: `CODE_INTELLIGENCE_SEVERITIES` in `autobot-frontend/src/types/codeIntelligence.ts`,
#: where a value the generated `Severity` does not carry fails to compile. Each is a
#: wire-format decision, not a refactor: #18098's "no serialized value changes, each is a
#: drop-in migration" does not hold for them. `Severity.score_ladder()` is the mechanism
#: if they migrate.
#:
#: `OptimizationPriority` also ranks urgency rather than severity, which is a second
#: question to answer before folding it in.
PENDING_A_WIRE_DECISION = {
    "autobot-backend/code_intelligence/llm_pattern_analysis/types.py::OptimizationPriority": (
        "autobot-backend/code_intelligence/llm_pattern_analyzer.py"
    ),
    "autobot-backend/code_intelligence/performance_analysis/types.py::PerformanceSeverity": (
        "autobot-backend/api/code_intelligence.py"
    ),
    "autobot-backend/code_intelligence/redis_optimizer.py::OptimizationSeverity": (
        "autobot-backend/api/code_intelligence.py"
    ),
    "autobot-backend/code_intelligence/security/constants.py::SecuritySeverity": (
        "autobot-backend/api/code_intelligence.py"
    ),
    "autobot-backend/code_intelligence/testing_pattern_analyzer.py::TestPatternSeverity": (
        "autobot-backend/code_intelligence/testing_pattern_analyzer.py"
    ),
}

CANONICAL = "autobot_shared/status_enums.py::Severity"


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    # #15926: `tracked_paths` is the one git enumerator -- it builds the pathspec and
    # raises on an empty result, so a guard cannot report clean having enumerated
    # nothing. Three new guards of mine each re-ran `git ls-files` directly, which is
    # what `one_git_enumeration_15926_test` counts and refuses to let grow.
    return tuple(tracked_paths(repo_root(), "*.py"))


def _enums_in_tree(tree: ast.Module) -> list[tuple[str, frozenset[str]]]:
    """Every Enum subclass with its member names.

    The base is matched by unparsing it, not by looking for the literal word "Enum":
    `from enum import Enum as _E` and `class X(enum.Enum)` both have to be caught, which
    is the fail-open `enum_union_guard_test.py` already shipped once and pinned.
    """
    found: list[tuple[str, frozenset[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = " ".join(ast.unparse(base) for base in node.bases)
        if "Enum" not in bases and "_E" not in bases:
            continue
        members = frozenset(
            target.id
            for stmt in node.body
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Constant)
            for target in stmt.targets
            if isinstance(target, ast.Name)
        )
        if members:
            found.append((node.name, members))
    return found


@functools.lru_cache(maxsize=1)
def _declared_enums() -> tuple[tuple[str, str, frozenset[str]], ...]:
    root = repo_root()
    declared: list[tuple[str, str, frozenset[str]]] = []
    for rel in _tracked_python_files():
        if not rel.startswith(tuple(f"{r}/" for r in SCANNED_ROOTS)):
            continue
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        declared.extend((rel, name, members) for name, members in _enums_in_tree(tree))
    return tuple(declared)


def test_the_scan_is_not_vacuous() -> None:
    """An empty sweep satisfies every assertion below by looking at nothing."""
    declared = _declared_enums()
    assert len(_tracked_python_files()) > 3000, "git ls-files returned almost nothing"
    assert len(declared) > 200, f"only {len(declared)} enums parsed — the roots are wrong"
    assert CANONICAL in {f"{rel}::{name}" for rel, name, _ in declared}


def test_the_scan_sees_an_enum_whose_base_was_imported_under_an_alias() -> None:
    """Matched against synthetic source, so it does not depend on the tree."""
    aliased = ast.parse("from enum import Enum as _E\n\n\nclass R(_E):\n    INFO = 'info'\n")
    assert _enums_in_tree(aliased) == [("R", frozenset({"INFO"}))]
    dotted = ast.parse("import enum\n\n\nclass D(enum.Enum):\n    INFO = 'info'\n")
    assert _enums_in_tree(dotted) == [("D", frozenset({"INFO"}))]


def test_no_new_severity_subset_enum_has_regrown() -> None:
    """Catch the next copy of the ladder, by member set rather than by name."""
    found = {f"{rel}::{name}" for rel, name, members in _declared_enums() if SEVERITY_SUBSET_PROBE <= members}
    assert found, "matched no enum at all — the probe is broken, not the tree"
    unexpected = found - set(PENDING_A_WIRE_DECISION) - {CANONICAL}
    assert not unexpected, (
        f"#18098: a severity ladder was re-declared instead of aliased to the canonical: "
        f"{sorted(unexpected)}. If it is a genuinely different scale, add it here with "
        "the reason; if it is a subset, alias it — `AntiPatternSeverity = Severity`."
    )


@pytest.mark.parametrize("entry", sorted(PENDING_A_WIRE_DECISION))
def test_every_pending_entry_still_names_a_real_enum(entry: str) -> None:
    """An allowlist entry stranded by a rename or a migration exempts nothing."""
    declared = {f"{rel}::{name}" for rel, name, _ in _declared_enums()}
    assert entry in declared, (
        f"#18098: {entry} names no enum any more. If it was aliased to the canonical, "
        "drop it from PENDING_A_WIRE_DECISION."
    )


@pytest.mark.parametrize("entry", sorted(PENDING_A_WIRE_DECISION))
def test_every_pending_entry_is_still_iterated(entry: str) -> None:
    """The exemption's stated reason must stay true, or the exemption is stale.

    Each of these is held back only because a dict key set is built by iterating its
    members. The day that stops being true it is a plain exact subset and should be
    aliased — and nothing else would ever say so.
    """
    name = entry.split("::", 1)[1]
    source = (repo_root() / PENDING_A_WIRE_DECISION[entry]).read_text(encoding="utf-8")
    assert f"in {name}" in source, (
        f"#18098: {entry} is exempt because {PENDING_A_WIRE_DECISION[entry]} iterates its "
        "member set, and that iteration is gone. Alias it and drop the exemption."
    )


def test_the_scope_this_guard_does_not_cover_is_recorded() -> None:
    """Stated rather than implied, so "green" is not read as "clean"."""
    scanned = {rel.split("/", 1)[0] for rel, _, _ in _declared_enums()}
    assert scanned <= set(SCANNED_ROOTS)
    assert "autobot-slm-backend" not in scanned, (
        "slm-backend is out of scope on purpose — its two severity enums are "
        "(str, Enum) persisted to indexed columns, so aliasing them is a migration"
    )
