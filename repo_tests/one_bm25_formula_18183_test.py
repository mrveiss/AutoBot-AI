# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One BM25 length-normalisation formula (#18183).

The tf-saturation denominator `tf + k1 * (1 - b + b * dl / avgdl)` lives once, in
`autobot-backend/knowledge/search_components/bm25.py` (`bm25_tf_component`). The marker is
the syntax shape `1 - X + X * ...`: a `+` whose left side is `1 - X`. Prose and comments
that name the formula are not a definition.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot-backend/knowledge/search_components/bm25.py"
_DEFERRED: tuple[str, ...] = ()


def _is_one(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value in (1, 1.0) and not isinstance(node.value, bool)


def _has_bm25_length_norm(source: str) -> bool:
    """True when `source` computes `1 - X + X * ...` (the Okapi length normalisation)."""
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Add)
            and isinstance(node.left, ast.BinOp)
            and isinstance(node.left.op, ast.Sub)
            and _is_one(node.left.left)
            and isinstance(node.right, ast.BinOp)
            and isinstance(node.right.op, (ast.Mult, ast.Div))
            and ast.dump(node.left.right) in {ast.dump(n) for n in ast.walk(node.right)}
        ):
            return True
    return False


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot-slm-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "one-bm25-formula",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=3228,  # re-pinned mid-window (train 73): population 3250, window [2950, 3250] (#17844)
    what="non-test python source",
    roots=("autobot-backend", "autobot-slm-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _holders() -> tuple[str, ...]:
    root = repo_root()
    return tuple(rel for rel in REACH.examined(root) if _scan(root / rel))


def _scan(path: Path) -> bool:
    return _has_bm25_length_norm(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("self-attribute copy", "d = tf + self.k1 * (1 - self.b + self.b * dl / avg)\n", True),
        ("float literal copy", "d = tf + k1 * (1.0 - b + b * dl / avg)\n", True),
        ("a comment naming it", "# tf + k1 * (1 - b + b * dl / avg)\nx = 1\n", False),
        ("a docstring naming it", '"""1 - b + b * dl / avg"""\n', False),
        ("an unrelated 1 - x + y", "z = 1 - x + y * w\n", False),
        ("a call to the shared helper", "d = bm25_tf_component(tf, dl, avg, k1, b)\n", False),
    ],
)
def test_the_matcher_tells_a_copy_from_a_use(label: str, source: str, expected: bool) -> None:
    assert _has_bm25_length_norm(source) is expected, label


def test_the_scan_is_not_vacuous() -> None:
    assert _CANONICAL in _holders(), "the canonical formula was not found: the scan is blind"


def test_no_second_bm25_formula() -> None:
    extra = sorted(set(_holders()) - {_CANONICAL} - set(_DEFERRED))
    assert not extra, (
        f"#18183: {extra} compute their own BM25 length normalisation; call "
        f"`bm25_tf_component`/`bm25_score_terms` from {_CANONICAL} instead of copying it."
    )


def test_the_deferral_is_still_needed() -> None:
    stale = [rel for rel in _DEFERRED if rel not in _holders()]
    assert not stale, f"#18183: {stale} no longer copy the formula; empty `_DEFERRED` in this guard."
