# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One graph score blend, one reranker-weight home, one RAG config for graph-RAG (#18141).

Graph-RAG, the mesh retriever and the cross-encoder reranker each blended a graph or vector
signal with their own formula and their own constants, and the mesh path skipped the reranker
weights, MMR and the stale-chunk filter the others ran (recurrences of #2103 and #4721).

* The graph blend, `(1 - graph_weight) * a + graph_weight * b`, lives once in
  `autobot_shared/graph_retrieval.py`.
* A numeric reranker weight is written once: the `RerankWeights` dataclass defaults in
  `knowledge/search_components/reranking.py`. Nobody else builds `RerankWeights(<number>)`, and
  nobody else hardcodes the legacy `0.8 * reranker + 0.2 * vector` split.
* Every mesh `rerank(...)` call forwards the configured weights, graph-RAG's RAGService is built
  from the shared config rather than a private `RAGConfig(...)`, and the mesh branch runs the
  stale-chunk filter.

All three detectors read the syntax tree, so a docstring or comment describing a formula is not
a definition.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL_BLEND = "autobot_shared/graph_retrieval.py"
_CANONICAL_WEIGHTS = "autobot-backend/knowledge/search_components/reranking.py"
_MESH = "autobot-backend/services/neural_mesh_retriever.py"
_RAG_SERVICE = "autobot-backend/services/rag_service.py"
_LIFESPAN = "autobot-backend/initialization/lifespan.py"
_ROOTS = ("autobot-backend", "autobot_shared")


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    """Non-test Python under both roots. Empty (not an exception) on an empty tree, for REACH."""
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "rag-blend-single-source-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(): see the PR for the arithmetic.
    floor=2579,
    what="non-test python source",
    roots=_ROOTS,
    growth=300,
)


# ---------------------------------------------------------------------------------------
# Detector 1: a local graph blend
# ---------------------------------------------------------------------------------------


def _mentions_graph_weight(node: ast.AST) -> bool:
    return "graph_weight" in ast.unparse(node)


def _is_one_minus(node: ast.AST) -> ast.AST | None:
    """``1 - X`` / ``1.0 - X`` -> X, else None."""
    if (
        isinstance(node, ast.BinOp)
        and isinstance(node.op, ast.Sub)
        and isinstance(node.left, ast.Constant)
        and node.left.value == 1
    ):
        return node.right
    return None


def _factors(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return _factors(node.left) + _factors(node.right)
    return [node]


def _is_local_graph_blend(node: ast.AST) -> bool:
    """``(1 - w) * a + w * b`` where ``w`` is a graph weight."""
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)):
        return False
    for first, second in ((node.left, node.right), (node.right, node.left)):
        for f in _factors(first):
            inner = _is_one_minus(f)
            if inner is not None and _mentions_graph_weight(inner):
                if any(ast.dump(g) == ast.dump(inner) for g in _factors(second)):
                    return True
    return False


def _has_local_graph_blend(source: str) -> bool:
    return any(_is_local_graph_blend(n) for n in ast.walk(ast.parse(source)))


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("graph-rag's old inline blend", "h = (1.0 - self.graph_weight) * base + self.graph_weight * prox\n", True),
        ("the same blend, terms swapped", "h = w.graph_weight * x + (1 - w.graph_weight) * y\n", True),
        ("a call to the shared blend", "h = blend_graph_score(base, base * s, self.graph_weight)\n", False),
        ("an unrelated moving average", "ema = (1 - alpha) * old + alpha * new\n", False),
        ("a comment naming the formula", "# (1 - graph_weight) * a + graph_weight * b\nx = 1\n", False),
        ("a docstring naming the formula", 'def f():\n    """(1 - graph_weight) * a + graph_weight * b"""\n', False),
    ],
)
def test_the_blend_matcher_tells_a_formula_from_a_mention(label: str, source: str, expected: bool) -> None:
    assert _has_local_graph_blend(source) is expected, label


# ---------------------------------------------------------------------------------------
# Detector 2: a reranker-weight literal
# ---------------------------------------------------------------------------------------


def _is_number(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)


def _is_legacy_split(node: ast.AST) -> bool:
    """``0.8 * reranker + 0.2 * vector`` -- the split `RerankWeights` replaced (#2004)."""
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)):
        return False
    consts = []
    for side in (node.left, node.right):
        nums = [f.value for f in _factors(side) if _is_number(f)]
        if len(nums) != 1 or len(_factors(side)) < 2:
            return False
        consts.append(nums[0])
    # A 0.8/0.2 moving average is not a rerank blend: the operands must be reranker/vector scores.
    operands = ast.unparse(node).lower()
    return sorted(consts) == [0.2, 0.8] and ("rerank" in operands or "vector" in operands)


def _is_weights_literal(node: ast.AST) -> bool:
    """``RerankWeights(<number>, ...)`` / ``RerankWeights(vector=<number>)``."""
    if not (isinstance(node, ast.Call) and ast.unparse(node.func).rsplit(".", 1)[-1] == "RerankWeights"):
        return False
    return any(_is_number(a) for a in node.args) or any(_is_number(k.value) for k in node.keywords)


def _weight_literals(source: str) -> int:
    return sum(_is_weights_literal(n) or _is_legacy_split(n) for n in ast.walk(ast.parse(source)))


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a keyword literal", "w = RerankWeights(reranker=0.7, vector=0.3)\n", 1),
        ("a positional literal", "w = RerankWeights(0.7, 0.3)\n", 1),
        ("the legacy hardcoded split", "s = 0.8 * reranker_score + 0.2 * vector_score\n", 1),
        ("the legacy split, terms swapped", "s = vector_score * 0.2 + rerank_score * 0.8\n", 1),
        ("a 0.8/0.2 moving average", "f = (f * 0.8) + (new_frequency * 0.2)\n", 0),
        ("defaults", "w = RerankWeights()\n", 0),
        ("splatted from config", "w = RerankWeights(**cfg)\n", 0),
        ("taken from config", "w = RerankWeights(reranker=cfg.reranker)\n", 0),
        ("another split", "s = 0.7 * a + 0.3 * b\n", 0),
        ("a comment", "# RerankWeights(0.7, 0.3) and 0.8 * reranker + 0.2 * vector\nx = 1\n", 0),
    ],
)
def test_the_weight_matcher_tells_a_literal_from_a_reference(label: str, source: str, expected: int) -> None:
    assert _weight_literals(source) == expected, label


# ---------------------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------------------


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[tuple[str, ...], tuple[str, ...], int]:
    """(files with a local graph blend, files with a weight literal, files parsed)."""
    blends: list[str] = []
    literals: list[str] = []
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = _read(rel)
        if "graph_weight" not in source and "0.8" not in source and "RerankWeights" not in source:
            continue
        parsed += 1
        if rel != _CANONICAL_BLEND and _has_local_graph_blend(source):
            blends.append(rel)
        if rel != _CANONICAL_WEIGHTS and _weight_literals(source):
            literals.append(rel)
    return tuple(blends), tuple(literals), parsed


def test_the_scan_is_not_vacuous() -> None:
    """graph-RAG, the mesh retriever, RAGConfig and the optimizer all mention these; fewer is blind."""
    assert _scan()[2] >= 4, f"parsed {_scan()[2]} files that mention a graph weight or reranker weights"


def test_the_graph_blend_lives_once() -> None:
    blends, _, _ = _scan()
    assert not blends, (
        f"#18141: {list(blends)} blend a graph signal locally; call "
        f"`blend_graph_score` from {_CANONICAL_BLEND} so every retrieval path scores alike."
    )


def test_reranker_weights_are_written_once() -> None:
    _, literals, _ = _scan()
    assert not literals, (
        f"#18141: {list(literals)} hardcode reranker weights; take `RAGConfig.rerank_weights` "
        f"or the defaults in {_CANONICAL_WEIGHTS}."
    )


# ---------------------------------------------------------------------------------------
# Wiring: the mesh path and graph-RAG's service go through the shared config and passes
# ---------------------------------------------------------------------------------------


def _rerank_calls_without_weights(source: str) -> list[int]:
    """Line numbers of ``<x>.rerank(...)`` calls that do not pass ``weights=``."""
    return [
        n.lineno
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "rerank"
        and not any(k.arg == "weights" for k in n.keywords)
    ]


def _constructs(source: str, name: str) -> bool:
    return any(
        isinstance(n, ast.Call) and ast.unparse(n.func).rsplit(".", 1)[-1] == name for n in ast.walk(ast.parse(source))
    )


def _calls_method(source: str, func: str, method: str) -> bool:
    """True when function ``func`` calls ``<anything>.<method>(...)``."""
    for fn in ast.walk(ast.parse(source)):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name == func:
            return any(
                isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == method
                for n in ast.walk(fn)
            )
    return False


def test_the_wiring_matchers_fire_on_the_forks_they_guard() -> None:
    assert _rerank_calls_without_weights("await self.reranker.rerank(q, m, top_k=3)\n") == [1]
    assert _rerank_calls_without_weights("await self.reranker.rerank(q, m, weights=w)\n") == []
    assert _constructs("c = RAGConfig(timeout_seconds=10.0)\n", "RAGConfig")
    assert not _constructs("c = get_rag_config()\n", "RAGConfig")
    assert _calls_method("async def f(s):\n    await s._filter_stale_chunks(r)\n", "f", "_filter_stale_chunks")
    assert not _calls_method("async def f(s):\n    return r\n", "f", "_filter_stale_chunks")
    assert not _calls_method("async def g(s):\n    s._filter_stale_chunks(r)\n", "f", "_filter_stale_chunks")


def test_every_mesh_rerank_forwards_the_configured_weights() -> None:
    assert (
        _rerank_calls_without_weights(_read(_MESH)) == []
    ), "#18141: a mesh rerank() call ignores RAGConfig.rerank_weights (the #2103 recurrence)"


def test_graph_rag_runs_on_the_shared_rag_config() -> None:
    assert not _constructs(_read(_LIFESPAN), "RAGConfig"), (
        "#18141: lifespan builds a private RAGConfig for graph-RAG; use the shared one so its "
        "timeout, rerank weights and graph weight cannot drift from the rest"
    )


def test_the_mesh_branch_runs_the_stale_filter() -> None:
    assert _calls_method(
        _read(_RAG_SERVICE), "_run_mesh_retriever", "_filter_stale_chunks"
    ), "#18141: the mesh branch returns before _filter_stale_chunks (the #4721 recurrence)"
