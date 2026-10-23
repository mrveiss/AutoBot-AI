# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One knowledge-base hybrid search (#17599).

`HybridSearchEngine` (`utils/hybrid_search.py`: naive term frequency, weighted-average
fusion) had one caller, the system validator, while the production path used
`HybridSearcher` (BM25 + semantic, reciprocal rank fusion). It was removed and the
validator now exercises `KnowledgeBase.search(mode="hybrid")`, which runs the canonical class.

The marker is a class that is named for hybrid search and that defines a search method. The
detector reads the syntax tree, so a docstring or comment naming the class is not a definition.
Pydantic request models share the name shape but define no search method.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = ("autobot-backend/knowledge/search_components/hybrid_search.py", "HybridSearcher")

#: Hybrid in a different sense, with no keyword leg: FAISS-GPU similarity over ChromaDB storage.
_NOT_A_KB_HYBRID = {
    ("autobot-backend/utils/gpu_vector_search.py", "HybridVectorSearch"): "FAISS + ChromaDB vectors only",
}

#: The validator must reach the canonical implementation through the knowledge base.
_VALIDATOR = "autobot-backend/utils/system_validator.py"


def _is_hybrid_search_class(node: ast.ClassDef) -> bool:
    named = "hybrid" in node.name.lower() and "search" in node.name.lower()
    searches = any(
        isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name.startswith("search") for m in node.body
    )
    return named and searches


def _hybrid_classes(source: str) -> list[str]:
    return [n.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ClassDef) and _is_hybrid_search_class(n)]


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "one-hybrid-search",
    discover=_source_population,
    # Mid-window, from REACH.window().
    floor=2702,
    what="non-test python source",
    roots=("autobot-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _found() -> tuple[tuple[str, str], ...]:
    found: list[tuple[str, str]] = []
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if "earch" not in source:
            continue
        found.extend((rel, name) for name in _hybrid_classes(source))
    return tuple(found)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a hybrid engine", "class HybridSearchEngine:\n    async def search(self): ...\n", ["HybridSearchEngine"]),
        ("a fusing searcher", "class HybridSearcher:\n    def search_with_x(self): ...\n", ["HybridSearcher"]),
        ("a request model", "class HybridSearchRequest(BaseModel):\n    q: str\n", []),
        ("a search class that is not hybrid", "class KeywordSearcher:\n    def search(self): ...\n", []),
        ("a docstring naming it", 'class A:\n    """HybridSearchEngine.search"""\n', []),
    ],
)
def test_the_matcher_tells_a_hybrid_search_from_its_lookalikes(label: str, source: str, expected: list[str]) -> None:
    assert _hybrid_classes(source) == expected, label


def test_the_scan_is_not_vacuous() -> None:
    """The canonical class is in the examined set; failing to find it means a blind scan."""
    assert _CANONICAL in _found(), f"{_CANONICAL} not found among {_found()}"


def test_one_knowledge_base_hybrid_search_exists() -> None:
    extra = [f for f in _found() if f != _CANONICAL and f not in _NOT_A_KB_HYBRID]
    assert not extra, (
        f"#17599: {extra} define a hybrid search beside {_CANONICAL}. Extend HybridSearcher "
        "(a new view or a fusion option) instead of writing a second engine."
    )


def test_the_validator_exercises_the_canonical_search() -> None:
    source = (repo_root() / _VALIDATOR).read_text(encoding="utf-8")
    assert (
        "SEARCH_MODE_HYBRID" in source
    ), f"#17599: {_VALIDATOR} no longer validates KnowledgeBase.search in hybrid mode"
