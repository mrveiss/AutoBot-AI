# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge search modes have ONE home: ``CategoryDefaults.SEARCH_MODE_*`` / ``SEARCH_MODES`` (#19335).

Two allow-lists disagreed: ``schemas_knowledge._VALID_SEARCH_MODES`` (semantic, keyword, hybrid,
auto -- the one the API validates with) and an unread ``knowledge_search.VALID_SEARCH_MODES``
(vector, text, auto). The live vocabulary now lives in ``autobot_shared/ssot_constants.py``.

A copy comes back in two shapes, both flagged in non-test backend modules: a collection literal
naming two or more search modes, and a ``mode``/``*search_mode*`` binding or default set to a
mode literal. ``"auto"`` alone is not read as a search mode -- the word is too common.

Accepted blind spots (the tree is clean of them today; a reviewer reads the diff for them): an
``Enum`` body such as ``HYBRID = "hybrid"``, a single-member ``Literal["hybrid"]``, and a
``Field``/``Query(default="hybrid")`` on a parameter not named ``mode``/``*search_mode*``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.ssot_constants import CategoryDefaults

_ROOT = "autobot-backend"
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
_MODES = frozenset({"semantic", "keyword", "hybrid", "auto"})
_DISTINCT = _MODES - {"auto"}
_MODE_NAME = re.compile(r"^(mode|.*search_mode.*)$", re.IGNORECASE)


def _modules(root: Path) -> list[Path]:
    base = root / _ROOT
    if not base.is_dir():
        return []
    return [p for p in sorted(base.rglob("*.py")) if not _TEST.search(p.relative_to(root).as_posix())]


#: 2,695 non-test backend modules measured at #19335; repinned by scripts/repin_reach_floors.py.
REACH = declare(
    "search-mode-copies",
    discover=_modules,
    floor=2500,
    growth=250,  # ~9%: ordinary backend growth between repins must not turn an unrelated PR red
    what="non-test backend modules",
    roots=(_ROOT,),
)


def _mode_literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and node.value in _DISTINCT:
        return node.value
    return None


def _collection_hit(node: ast.AST) -> bool:
    if not isinstance(node, ast.Set | ast.Tuple | ast.List):
        return False
    named = {e.value for e in node.elts if isinstance(e, ast.Constant) and e.value in _MODES}
    return len(named & _DISTINCT) >= 1 and len(named) >= 2


def _binding_hits(node: ast.AST) -> list[str]:
    """``mode = "hybrid"``, ``mode: str = "hybrid"`` and ``def f(mode="hybrid")``."""
    hits = []
    if isinstance(node, ast.AnnAssign | ast.Assign):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(t, ast.Name) and _MODE_NAME.match(t.id) for t in targets) and _mode_literal(node.value):
            hits.append(_mode_literal(node.value))
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        args = node.args.args[len(node.args.args) - len(node.args.defaults) :]
        pairs = list(zip(args, node.args.defaults)) + list(zip(node.args.kwonlyargs, node.args.kw_defaults))
        hits += [_mode_literal(d) for a, d in pairs if _MODE_NAME.match(a.arg) and _mode_literal(d)]
    return hits


def mode_copies(source: str, rel: str) -> list[str]:
    """Each place *source* restates the search-mode vocabulary."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if _collection_hit(node):
            found.append(f"{rel}:{node.lineno}: a search-mode list literal")
        found += [f"{rel}:{node.lineno}: mode defaults to the literal {m!r}" for m in _binding_hits(node)]
    return found


def test_search_modes_have_one_home_on_the_live_tree() -> None:
    root = repo_root()
    files = REACH.examined(root)
    found = [h for p in files for h in mode_copies(p.read_text(encoding="utf-8"), p.relative_to(root).as_posix())]
    REACH.completed(files)
    assert not found, f"use CategoryDefaults.SEARCH_MODE_* / SEARCH_MODES (#19335): {found}"


def test_the_home_lists_exactly_the_modes_the_api_accepts() -> None:
    assert set(CategoryDefaults.SEARCH_MODES) == _MODES


@pytest.mark.parametrize(
    "source",
    [
        'VALID = ("semantic", "keyword", "hybrid", "auto")\n',
        'MODES = {"keyword", "auto"}\n',
        'mode: str = "hybrid"\n',
        'def search(q, mode="semantic"): ...\n',
        'async def search(q, *, search_mode="keyword"): ...\n',
    ],
)
def test_each_copy_shape_is_flagged(source: str) -> None:
    assert mode_copies(source, "x.py")


def test_the_constants_and_unrelated_words_are_not_copies() -> None:
    clean = (
        "mode: str = CategoryDefaults.SEARCH_MODE_HYBRID\n"
        'def f(mode="auto"): ...\n'
        'COLOURS = ("hybrid-car", "auto")\n'
        'dispatch = {"text": 1, "vector": 2}\n'
    )
    assert not mode_copies(clean, "x.py")
