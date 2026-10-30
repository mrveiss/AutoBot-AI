# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Knowledge search modes have ONE home: ``CategoryDefaults.SEARCH_MODE_*`` / ``SEARCH_MODES`` (#19335).

Two allow-lists disagreed: ``schemas_knowledge._VALID_SEARCH_MODES`` (semantic, keyword, hybrid,
auto -- the one the API validates with) and an unread ``knowledge_search.VALID_SEARCH_MODES``
(vector, text, auto). The live vocabulary now lives in ``autobot_shared/ssot_constants.py``.

A copy comes back in three shapes, all flagged in non-test backend modules: a collection literal
naming two or more search modes, a ``mode``/``*search_mode*`` binding or default set to a mode
literal (``"auto"`` included, #19698: on a parameter or variable NAMED ``mode`` it is the mode),
and a pattern or regex string that spells two or more modes joined by ``|`` (the ``Field(pattern=)``
allow-list at ``schemas_knowledge.ScopedSearchRequest.mode``, #19698). ``"auto"`` in a collection
is still not read as a search mode on its own -- the word is too common.

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
    floor=2607,  # mid-window: population 2732, window (2482, 2732)
    growth=250,  # ~9%: ordinary backend growth between repins must not turn an unrelated PR red
    what="non-test backend modules",
    roots=(_ROOT,),
)


_ALTERNATION = re.compile(r"\b(semantic|keyword|hybrid|auto)\b\s*\|\s*\(?\??:?(semantic|keyword|hybrid|auto)\b")


def _mode_literal(node: ast.AST | None, *, auto: bool = False) -> str | None:
    """The mode literal *node* is, read through ``Field(default=...)``. ``"auto"`` counts only where
    *auto* says the scope is a search."""
    if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "Field":
        node = next((k.value for k in node.keywords if k.arg == "default"), node.args[0] if node.args else None)
    if isinstance(node, ast.Constant) and node.value in (_MODES if auto else _DISTINCT):
        return node.value
    return None


def _collection_hit(node: ast.AST) -> bool:
    if not isinstance(node, ast.Set | ast.Tuple | ast.List):
        return False
    named = {e.value for e in node.elts if isinstance(e, ast.Constant) and e.value in _MODES}
    return len(named & _DISTINCT) >= 1 and len(named) >= 2


def _pattern_hit(node: ast.AST) -> bool:
    """A string spelling two search modes as a regex alternation, e.g. ``^(semantic|keyword|...)$``."""
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and bool(_ALTERNATION.search(node.value))


def _is_search(name: str) -> bool:
    return "search" in name.lower()


def _assign_hits(node: ast.AST, search_scope: bool) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    hits = []
    for t in targets:
        if isinstance(t, ast.Name) and _MODE_NAME.match(t.id):
            hit = _mode_literal(node.value, auto=search_scope or _is_search(t.id))
            hits += [hit] if hit else []
    return hits


def _binding_hits(node: ast.AST, scope: tuple[str, bool] = ("", False)) -> list[str]:
    """``mode = "hybrid"``, ``mode: str = "hybrid"`` and ``def f(mode="hybrid")``.

    ``"auto"`` is read only inside a scope (function or class) whose name says *search*, or on a
    ``*search_mode*`` name: ``mode="auto"`` is also an extraction, protection or retrieval-strategy
    mode elsewhere, and those are other vocabularies (#19698).
    """
    name, in_class = scope
    hits = []
    if isinstance(node, ast.AnnAssign | ast.Assign) and node.value is not None:
        hits += _assign_hits(node, _is_search(name))
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        # A method's search class counts (``SearchRequest.__init__``); an enclosing function does not.
        search = _is_search(node.name) or (in_class and _is_search(name))
        args = node.args.args[len(node.args.args) - len(node.args.defaults) :]
        pairs = list(zip(args, node.args.defaults)) + list(zip(node.args.kwonlyargs, node.args.kw_defaults))
        for a, d in pairs:
            hit = _mode_literal(d, auto=search or _is_search(a.arg)) if _MODE_NAME.match(a.arg) else None
            hits += [hit] if hit else []
    return hits


def _scopes(tree: ast.AST) -> dict[int, tuple[str, bool]]:
    """``id(node) -> (name, is a class)`` of the nearest enclosing function or class."""
    scope: dict[int, tuple[str, bool]] = {}
    stack: list[tuple[ast.AST, tuple[str, bool]]] = [(tree, ("", False))]
    while stack:
        node, here = stack.pop()
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            here = (node.name, isinstance(node, ast.ClassDef))
        for child in ast.iter_child_nodes(node):
            scope[id(child)] = here
            stack.append((child, here))
    return scope


def mode_copies(source: str, rel: str) -> list[str]:
    """Each place *source* restates the search-mode vocabulary."""
    found = []
    tree = ast.parse(source)
    scope = _scopes(tree)
    for node in ast.walk(tree):
        if _collection_hit(node):
            found.append(f"{rel}:{node.lineno}: a search-mode list literal")
        if _pattern_hit(node):
            found.append(f"{rel}:{node.lineno}: a pattern/regex literal spelling the search modes")
        found += [
            f"{rel}:{node.lineno}: mode defaults to the literal {m!r}"
            for m in _binding_hits(node, scope.get(id(node), ("", False)))
        ]
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
        'def search(q, mode="auto"): ...\n',
        'def search(q, *, mode: str = "auto"): ...\n',
        'async def hybrid_search(q, mode: str = "auto"): ...\n',
        'class SearchRequest(BaseModel):\n    mode: str = "auto"\n',
        'search_mode = "auto"\n',
        'def search(q):\n    if q:\n        try:\n            mode = "auto"\n        finally:\n            pass\n',
        'async def search(q):\n    with ctx():\n        mode: str = "auto"\n',
        'class SearchRequest(BaseModel):\n    mode: str = Field(default="auto")\n',
        'class R(BaseModel):\n    mode: str = Field("hybrid", description="x")\n',
        'class SearchRequest:\n    def __init__(self, mode="auto"): ...\n',
        'class R(BaseModel):\n    mode: str = Field(default="x", pattern=r"^(semantic|keyword|hybrid|auto)\\z")\n',
        'RX = "keyword|hybrid"\n',
    ],
)
def test_each_copy_shape_is_flagged(source: str) -> None:
    assert mode_copies(source, "x.py")


def test_the_constants_and_unrelated_words_are_not_copies() -> None:
    clean = (
        "mode: str = CategoryDefaults.SEARCH_MODE_HYBRID\n"
        "def f(mode=CategoryDefaults.SEARCH_MODE_AUTO): ...\n"
        'def g(engine="auto", fmt="hybrid-car"): ...\n'
        'def get_context(q, mode: str = "auto"): ...\n'
        'def search(q):\n    def extract(mode="auto"): ...\n    if q:\n        cfg = "auto"\n'
        'class Extractor:\n    mode: str = Field(default="auto")\n'
        "class R(BaseModel):\n    limit: int = Field(default=5)\n"
        'class Extractor:\n    def __init__(self, mode: str = "auto"): ...\n'
        'class R(BaseModel):\n    x: str = Field(pattern="^(" + "|".join(MODES) + ")$")\n'
        'PAT = "auto|manual"\n'
        'COLOURS = ("hybrid-car", "auto")\n'
        'dispatch = {"text": 1, "vector": 2}\n'
    )
    assert not mode_copies(clean, "x.py")
