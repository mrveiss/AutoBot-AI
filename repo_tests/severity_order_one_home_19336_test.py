# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Severity ORDER has one home: ``autobot_shared.status_enums.Severity.rank`` (#19336).

Six hand-written orderings disagreed in vocabulary and direction (ascending tuples, descending
tuples, rank-0-is-worst dicts), so a sort over one copy inverted on another. Same-concept copies
now sort by ``Severity.rank`` / ``Severity.rank_of``; other domains carry their own names
(``_CONFLICT_COMPLEXITY_ORDER``, ``NPM_ADVISORY_ORDER``, ``PROBLEM_SEVERITY_ORDER`` -- the last
has ``hint``, which ``Severity`` deliberately lacks).

A copy comes back as a literal that orders the ``Severity`` vocabulary itself: a tuple/list made
only of severity words (three or more), or a dict mapping three or more of them to integer ranks.

The six orderings #19336 listed are gone; the sweep then measured 43 more (24 after the analytics endpoints and sort-key sites batch) hand-written severity
sequences across the backends (the class's remainder, listed and sampled on #19336). ``PIN`` holds that count
exactly and only goes down against the base: each follow-up batch lowers it by what it converts.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

from autobot_shared.status_enums import Severity

_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared", "pipeline-scripts")
_HOME = "autobot_shared/status_enums.py"
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
_WORDS = frozenset(member.value for member in Severity)
_THIS = "repo_tests/severity_order_one_home_19336_test.py"

#: Hand-written severity sequences still in the tree (measured at #19336). Down-only, exact.
PIN = {"severity_order_copies": 24}


def _modules(root: Path) -> list[Path]:
    found = []
    for top in _ROOTS:
        base = root / top
        if base.is_dir():
            found += [p for p in sorted(base.rglob("*.py")) if not _TEST.search(p.relative_to(root).as_posix())]
    return found


REACH = declare(
    "severity-order-copies",
    discover=_modules,
    floor=3298,  # mid-window: population 3448, window (3148, 3448)
    growth=300,  # ~9%: ordinary growth between repins must not turn an unrelated PR red
    what="non-test Python modules",
    roots=_ROOTS,
)


def _strings(nodes: list[ast.AST]) -> list[str] | None:
    """The string values of *nodes*, or None if any is not a string constant."""
    values = [n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    return values if len(values) == len(nodes) else None


def _is_int(node: ast.AST) -> bool:
    """An int literal, including a negative one (``-1`` parses as a unary minus)."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    return isinstance(node, ast.Constant) and type(node.value) is int


def _is_ordering(node: ast.AST) -> bool:
    if isinstance(node, ast.Tuple | ast.List):
        words = _strings(node.elts)
        return words is not None and len(words) >= 3 and set(words) <= _WORDS
    if isinstance(node, ast.Dict) and node.keys and None not in node.keys:
        words = _strings(node.keys)
        ints = all(_is_int(v) for v in node.values)
        distinct = len({ast.dump(v) for v in node.values}) == len(node.values)  # a count dict repeats values
        return words is not None and len(words) >= 3 and set(words) <= _WORDS and ints and distinct
    return False


def order_copies(source: str, rel: str) -> list[str]:
    """Each literal in *source* that orders the Severity vocabulary by hand."""
    if rel == _HOME:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []  # a file that does not parse is another guard's finding, not a red here for everyone
    return [f"{rel}:{n.lineno}: a hand-written severity order" for n in ast.walk(tree) if _is_ordering(n)]


def test_no_new_hand_written_severity_order() -> None:
    root = repo_root()
    files = REACH.examined(root)
    found = [h for p in files for h in order_copies(p.read_text(encoding="utf-8"), p.relative_to(root).as_posix())]
    REACH.completed(files)
    pinned = PIN["severity_order_copies"]
    assert (
        len(found) <= pinned
    ), f"sort or filter by Severity.rank / Severity.rank_of (#19336); new copies among: {found}"
    assert len(found) == pinned, f"{len(found)} hand-written severity orders, pin says {pinned}: lower PIN in this PR"


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), (_THIS,), "PIN")
    if base:
        assert PIN["severity_order_copies"] <= base["severity_order_copies"], "the pin only goes down (#19336)"


def test_the_home_ranks_in_declaration_order() -> None:
    ladder = [Severity.UNKNOWN, Severity.INFO, Severity.MINIMAL, Severity.LOW, Severity.WARNING, Severity.MEDIUM]
    ladder += [Severity.DEGRADED, Severity.HIGH, Severity.ERROR, Severity.CRITICAL]
    assert [s.rank for s in ladder] == sorted(s.rank for s in ladder), "every caller sorts by this order"
    assert Severity.rank_of(Severity.HIGH) == Severity.HIGH.rank, "a member is ranked, not treated as unknown"
    assert Severity.rank_of("High") == Severity.HIGH.rank and Severity.rank_of("hint") == -1


@pytest.mark.parametrize(
    "source",
    [
        '_SEVERITY_ORDER = ("high", "medium", "low")\n',
        '_SEVERITY_ORDER = ("info", "low", "medium", "high", "critical")\n',
        'ORDER = {"high": 0, "medium": 1, "low": 2}\n',
        'RANK = {"high": -1, "medium": -2, "low": -3}\n',
        'for s in ["critical", "high", "medium", "low"]: pass\n',
    ],
)
def test_each_hand_ordering_is_flagged(source: str) -> None:
    assert order_copies(source, "x.py")


def test_other_vocabularies_and_short_lists_are_not_copies() -> None:
    clean = (
        'P = ("high", "medium", "low", "info", "hint")\n'
        'NPM = ("critical", "high", "moderate", "low", "info")\n'
        'FAILING = ("critical", "high")\n'
        'LABELS = {"high": "H", "medium": "M", "low": "L"}\n'
        'COUNTS = {"critical": 0, "high": 0, "medium": 5}\n'
    )
    assert not order_copies(clean, "x.py")


def test_triage_ladder_derives_the_orderings_the_endpoints_used_to_spell_out() -> None:
    assert Severity.triage_ladder() == (Severity.LOW, Severity.MEDIUM, Severity.HIGH)
    assert [s.rank for s in Severity.triage_ladder()] == sorted(s.rank for s in Severity.triage_ladder())
    worst_first = (Severity.CRITICAL, *reversed(Severity.triage_ladder()))
    assert [s.value for s in worst_first] == ["critical", "high", "medium", "low"]
    risk = (Severity.CRITICAL, *reversed(Severity.triage_ladder()), Severity.MINIMAL)
    assert [s.value for s in risk] == ["critical", "high", "medium", "low", "minimal"]
    assert [s.value for s in reversed(Severity.finding_ladder())] == ["critical", "high", "medium", "low", "info"]
    assert [s.value for s in reversed(Severity.triage_ladder())] == ["high", "medium", "low"]


def test_the_risk_ladder_is_the_listing_the_risk_reports_used_to_spell_out() -> None:
    assert [s.value for s in Severity.risk_ladder()] == ["critical", "high", "medium", "low", "minimal"]
