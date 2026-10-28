# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: every RAG default and rule #19280 consolidated keeps exactly one definition.

Each test fails when a second definition is re-added:

* a literal traversal-depth default in ``autobot_memory_graph`` (the home is
  ``constants/rag_graph_constants.py``);
* a bare ``RerankWeights()`` that bypasses ``RAGConfig.rerank_weights``;
* a staleness key other than ``resolve_chunk_id`` (``chunk_id or id``);
* a second reader of the doc indexer's hash cache (the home is ``knowledge/stale_filter.py``);
* a string placeholder for a numeric RAGConfig field in an API docstring;
* ``docs/guides/rag-pdf-workflow.md`` restating a ``RAGConfig`` / ``RerankWeights`` default.
"""

from __future__ import annotations

import ast
import inspect
import re
from dataclasses import MISSING, fields
from pathlib import Path

import pytest

from constants.rag_graph_constants import RAG_GRAPH_PATH_DEPTH, RAG_GRAPH_TRAVERSAL_DEPTH, RAG_RELATION_DEPTH

BACKEND = Path(__file__).resolve().parents[1]
DEPTH_PARAMS = frozenset({"max_depth", "depth", "max_hops"})
SKIP_DIRS = frozenset({"tests", "node_modules", "__pycache__", "venv", ".venv"})
HASH_CACHE_HOMES = frozenset({"services/knowledge/doc_indexer.py", "knowledge/stale_filter.py"})
STALENESS_KEY_HOME = "knowledge/chunk_identity.py"
CHUNK_ID_OR = re.compile(r"""\.get\(\s*["']chunk_id["']\s*\)\s+or\s""")
RAG_GUIDE = BACKEND.parent / "docs" / "guides" / "rag-pdf-workflow.md"
# ``name: 0.3`` (yaml), ``"name": 0.3`` (json), ``name: float = 0.3`` / ``name=0.3`` (python).
NUMERIC_ASSIGNMENT = r"""\b{name}\b["'`]?\s*(?::\s*[A-Za-z_][\w\[\], |]*\s*)?[:=]\s*-?\d"""


def _source_files(root: Path) -> list[Path]:
    """Production .py files under *root*: no tests, no vendored or cache dirs."""
    return [
        p
        for p in root.rglob("*.py")
        if not SKIP_DIRS.intersection(p.relative_to(BACKEND).parts)
        and not p.name.endswith("_test.py")
        and not p.name.startswith("test_")
    ]


def _files_containing(needle: str) -> list[Path]:
    return [p for p in _source_files(BACKEND) if needle in p.read_text(encoding="utf-8")]


def _literal_depth_defaults(path: Path) -> list[str]:
    """``func:param=value`` for every depth parameter with a numeric literal default in *path*."""
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args.args + node.args.kwonlyargs
        defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + node.args.defaults
        defaults += node.args.kw_defaults
        for arg, default in zip(args, defaults):
            if arg.arg in DEPTH_PARAMS and isinstance(default, ast.Constant) and isinstance(default.value, int):
                found.append(f"{node.name}:{arg.arg}={default.value}")
    return found


def test_the_memory_graph_restates_no_traversal_depth_default():
    offenders = {
        str(p.relative_to(BACKEND)): hits
        for p in _source_files(BACKEND / "autobot_memory_graph")
        if (hits := _literal_depth_defaults(p))
    }
    assert offenders == {}


@pytest.mark.parametrize(
    ("func_path", "param", "expected"),
    [
        ("autobot_memory_graph.property_graph:PropertyGraph.multi_hop", "max_depth", RAG_GRAPH_TRAVERSAL_DEPTH),
        ("autobot_memory_graph.property_graph:PropertyGraph.subgraph", "max_depth", RAG_GRAPH_TRAVERSAL_DEPTH),
        ("autobot_memory_graph.property_graph:PropertyGraph.shortest_path", "max_depth", RAG_GRAPH_PATH_DEPTH),
        ("autobot_memory_graph.property_graph_mixin:PropertyGraphMixin.find_path", "max_depth", RAG_GRAPH_PATH_DEPTH),
        (
            "autobot_memory_graph.relation_traversal:RelationTraversalMixin.get_related_entities",
            "max_depth",
            RAG_RELATION_DEPTH,
        ),
    ],
)
def test_the_memory_graph_reads_its_depth_defaults_from_the_one_home(func_path, param, expected):
    import importlib

    module_name, qualname = func_path.split(":")
    owner_name, func_name = qualname.split(".")
    func = getattr(getattr(importlib.import_module(module_name), owner_name), func_name)
    assert inspect.signature(func).parameters[param].default == expected


def test_no_bare_rerank_weights_bypasses_rag_config():
    offenders = []
    for path in _files_containing("RerankWeights()"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            is_bare = isinstance(node, ast.Call) and not node.args and not node.keywords
            if is_bare and isinstance(node.func, ast.Name) and node.func.id == "RerankWeights":
                offenders.append(f"{path.relative_to(BACKEND)}:{node.lineno}")
    assert offenders == []


def test_staleness_is_keyed_by_resolve_chunk_id_only():
    offenders = [
        str(p.relative_to(BACKEND))
        for p in _files_containing("chunk_id")
        if str(p.relative_to(BACKEND)) != STALENESS_KEY_HOME and CHUNK_ID_OR.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_only_the_shared_stale_filter_reads_the_doc_hash_cache():
    readers = {str(p.relative_to(BACKEND)) for p in _files_containing("HASH_CACHE_FILE")}
    assert readers == HASH_CACHE_HOMES


def test_no_api_docstring_shows_a_string_for_a_numeric_rag_config_field():
    assert [str(p.relative_to(BACKEND)) for p in _files_containing('"<RAGConfig.')] == []


def test_the_bare_optimizer_and_the_mesh_fallback_read_rag_config_weights():
    from advanced_rag_optimizer import AdvancedRAGOptimizer
    from knowledge.search_components.reranking import ResultReranker
    from services.rag_config import get_rag_config, reset_rag_config, update_rag_config

    reset_rag_config()
    try:
        update_rag_config({"rerank_weights": {"reranker": 0.1, "vector": 0.9}})
        configured = get_rag_config().rerank_weights
        assert AdvancedRAGOptimizer()._rerank_weights == configured
        result = {"content": "c", "score": 1.0}
        ResultReranker()._apply_rerank_scores([result], [0.0], weights=None)
        assert result["rerank_score"] == pytest.approx((0.1 * 0.5 + 0.9 * 1.0) / 1.0)
    finally:
        reset_rag_config()


def _config_defaults() -> dict:
    """Every ``RAGConfig`` and ``RerankWeights`` field with its default value."""
    from knowledge.search_components.reranking import RerankWeights
    from services.rag_config import RAGConfig

    found = {}
    for cls in (RAGConfig, RerankWeights):
        for f in fields(cls):
            found[f.name] = f.default if f.default is not MISSING else None
    return found


def test_the_rag_guide_restates_no_rag_config_default():
    text = RAG_GUIDE.read_text(encoding="utf-8")
    defaults = _config_defaults()
    numeric = sorted(n for n in defaults if re.search(NUMERIC_ASSIGNMENT.format(name=re.escape(n)), text))
    literal = sorted(n for n, v in defaults.items() if isinstance(v, str) and len(v) > 8 and v in text)
    assert (numeric, literal) == ([], [])


def _literal_score_thresholds(source: str) -> list[str]:
    """``score_threshold`` given a non-zero numeric literal as a parameter default or a call keyword.

    0.0 is "no filtering" (e.g. models/task_context.py's generic SearchContext), not a retrieval floor.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            positional = node.args.posonlyargs + node.args.args
            args = positional + node.args.kwonlyargs
            defaults = [None] * (len(positional) - len(node.args.defaults)) + node.args.defaults
            pairs = zip(args, defaults + node.args.kw_defaults)
            found += [f"{node.name}:{a.arg}" for a, d in pairs if a.arg == "score_threshold" and _nonzero(d)]
        elif isinstance(node, ast.keyword) and node.arg == "score_threshold" and _nonzero(node.value):
            found.append(f"line {node.value.lineno}: score_threshold=")
        elif isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "score_threshold":
            found += ["field score_threshold"] if _nonzero(node.value) else []
    return found


def _nonzero(node) -> bool:
    """A non-zero numeric literal, signed (``-0.3`` is a ``UnaryOp`` over a ``Constant``) or not."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        node = node.operand
    return isinstance(node, ast.Constant) and isinstance(node.value, int | float) and node.value != 0


def test_the_retrieval_score_threshold_has_one_home():
    """#19354: every retrieval default reads constants.rag_graph_constants.RAG_SCORE_THRESHOLD."""
    found = [
        f"{p.relative_to(BACKEND)}: {hit}"
        for p in _files_containing("score_threshold")
        for hit in _literal_score_thresholds(p.read_text(encoding="utf-8"))
    ]
    assert not found, f"read RAG_SCORE_THRESHOLD from constants.rag_graph_constants (#19354): {found}"


@pytest.mark.parametrize(
    "source",
    [
        "def f(q, score_threshold: float = 0.3):\n    pass\n",
        "async def f(q, *, score_threshold=0.5):\n    pass\n",
        "svc.retrieve(q, score_threshold=0.3)\n",
        "class C:\n    score_threshold: float = 0.3\n",
        "def f(score_threshold=0.3, /):\n    pass\n",
        "def f(q, score_threshold=-0.3):\n    pass\n",
        "svc.retrieve(q, score_threshold=-0.2)\n",
    ],
)
def test_a_literal_score_threshold_is_flagged(source):
    assert _literal_score_thresholds(source)


def test_the_home_and_no_filtering_are_not_flagged():
    assert not _literal_score_thresholds("def f(q, score_threshold: float = RAG_SCORE_THRESHOLD):\n    pass\n")
    assert not _literal_score_thresholds("class C:\n    score_threshold: float = 0.0\n")


def test_the_unit_interval_rag_knobs_are_range_checked_at_runtime():
    """#19354 review: the registry's 0-1 range is enforced where the value is read, not only documented.

    Out-of-range and NaN values fall back to the default rather than being clamped (second review).
    """
    source = (BACKEND / "constants" / "rag_graph_constants.py").read_text(encoding="utf-8")
    calls = {
        node.args[0].value: node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant)
    }
    for name in ("AUTOBOT_RAG_SCORE_THRESHOLD", "AUTOBOT_RAG_GRAPH_WEIGHT"):
        call = calls[name]
        assert getattr(call.func, "id", "") == "env_unit_interval", f"{name} must be read range-checked"
        assert [a.value for a in call.args[1:2]] == [0.3], f"{name}: default 0.3"


@pytest.mark.parametrize("raw", ["nan", "inf", "-0.1", "1.5", "30"])
def test_an_invalid_unit_interval_value_falls_back_to_the_default(monkeypatch, raw):
    """NaN or a value outside 0-1 is refused, not clamped to a floor that admits or rejects everything."""
    from constants.rag_graph_constants import env_unit_interval

    monkeypatch.setenv("AUTOBOT_RAG_TEST_UNIT", raw)
    assert env_unit_interval("AUTOBOT_RAG_TEST_UNIT", 0.3) == 0.3


def test_a_valid_unit_interval_value_is_used(monkeypatch):
    from constants.rag_graph_constants import env_unit_interval

    monkeypatch.setenv("AUTOBOT_RAG_TEST_UNIT", "0.45")
    assert env_unit_interval("AUTOBOT_RAG_TEST_UNIT", 0.3) == 0.45
