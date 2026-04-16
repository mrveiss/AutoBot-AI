# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for CodeIndexer (#4820)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

tree_sitter_available = True
try:
    import tree_sitter_python  # noqa: F401
except ImportError:
    tree_sitter_available = False

requires_tree_sitter = pytest.mark.skipif(
    not tree_sitter_available,
    reason="tree-sitter-python not installed"
)

from services.knowledge.code_indexer import (
    CodeIndexer,
    _make_node_id,
    extract_python,
)

SIMPLE_PYTHON = b"""
def greet(name: str) -> str:
    return "hello " + name

class Greeter:
    def run(self) -> None:
        greet("world")
"""


def test_make_node_id_is_stable_and_lowercase():
    nid = _make_node_id("MyFunc", "src/auth.py")
    assert nid == "auth::myfunc"
    assert nid == _make_node_id("MyFunc", "src/auth.py")


@requires_tree_sitter
def test_extract_python_finds_function_nodes():
    result = extract_python("module.py", SIMPLE_PYTHON)
    node_names = [n["name"] for n in result["nodes"]]
    assert "greet" in node_names


@requires_tree_sitter
def test_extract_python_finds_class_nodes():
    result = extract_python("module.py", SIMPLE_PYTHON)
    node_names = [n["name"] for n in result["nodes"]]
    assert "Greeter" in node_names


@requires_tree_sitter
def test_extract_python_finds_call_edge():
    result = extract_python("module.py", SIMPLE_PYTHON)
    edge_pairs = [(e["source"], e["target_name"]) for e in result["edges"]]
    assert any(target == "greet" for _, target in edge_pairs)


@requires_tree_sitter
def test_extract_python_no_duplicate_edges():
    result = extract_python("module.py", SIMPLE_PYTHON)
    pairs = [(e["source"], e["target_name"]) for e in result["edges"]]
    assert len(pairs) == len(set(pairs))


def _make_indexer(tmp_path: Path):
    collection = MagicMock()
    collection.upsert = MagicMock()
    embed_model = MagicMock()
    embed_model.get_text_embedding = MagicMock(return_value=[0.1] * 384)
    cache_file = tmp_path / ".code_index_hashes.json"
    return CodeIndexer(collection=collection, embed_model=embed_model, cache_file=cache_file)


@requires_tree_sitter
def test_index_python_file_upserts_nodes(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    result = indexer.index_file(str(src), root_dir=str(tmp_path))
    assert result.success > 0
    assert indexer._collection.upsert.called


def test_index_unchanged_file_skips(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    indexer.index_file(str(src), root_dir=str(tmp_path))
    call_count_first = indexer._collection.upsert.call_count

    result = indexer.index_file(str(src), root_dir=str(tmp_path))
    assert result.skipped == 1
    assert indexer._collection.upsert.call_count == call_count_first


@requires_tree_sitter
def test_force_reindex_bypasses_cache(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    indexer.index_file(str(src), root_dir=str(tmp_path))
    call_count_first = indexer._collection.upsert.call_count

    result = indexer.index_file(str(src), root_dir=str(tmp_path), force=True)
    assert result.success > 0
    assert indexer._collection.upsert.call_count > call_count_first
