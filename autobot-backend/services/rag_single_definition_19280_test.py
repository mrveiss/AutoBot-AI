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
