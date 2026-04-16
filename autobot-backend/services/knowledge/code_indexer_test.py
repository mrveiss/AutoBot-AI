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
async def test_index_python_file_upserts_nodes(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_file(str(src), root_dir=str(tmp_path))
    assert result.success > 0
    assert indexer._collection.upsert.called


async def test_index_unchanged_file_skips(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    await indexer.index_file(str(src), root_dir=str(tmp_path))
    call_count_first = indexer._collection.upsert.call_count

    result = await indexer.index_file(str(src), root_dir=str(tmp_path))
    assert result.skipped == 1
    assert indexer._collection.upsert.call_count == call_count_first


@requires_tree_sitter
async def test_force_reindex_bypasses_cache(tmp_path):
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    await indexer.index_file(str(src), root_dir=str(tmp_path))
    call_count_first = indexer._collection.upsert.call_count

    result = await indexer.index_file(str(src), root_dir=str(tmp_path), force=True)
    assert result.success > 0
    assert indexer._collection.upsert.call_count > call_count_first


# ---------------------------------------------------------------------------
# index_directory — wiring tests (#4835)
# ---------------------------------------------------------------------------


@requires_tree_sitter
@pytest.mark.asyncio
async def test_index_directory_indexes_all_py_files(tmp_path):
    """index_directory walks a tree and indexes every .py file."""
    (tmp_path / "a.py").write_bytes(SIMPLE_PYTHON)
    (tmp_path / "b.py").write_bytes(b"def foo(): pass\n")
    (tmp_path / "README.md").write_bytes(b"# readme")  # should be skipped
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    # At least the nodes from a.py and b.py must be indexed
    assert result.success > 0
    assert result.failed == 0


@requires_tree_sitter
@pytest.mark.asyncio
async def test_index_directory_skips_hidden_dirs(tmp_path):
    """index_directory skips files inside .git and similar hidden directories."""
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "hook.py").write_bytes(b"def x(): pass\n")
    (tmp_path / "real.py").write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    # Only real.py nodes should be indexed; hidden dir is skipped
    assert result.success > 0
    # Verify hidden file was not touched
    upserted_ids = [
        call_args[1]["ids"][0]
        for call_args in indexer._collection.upsert.call_args_list
    ]
    assert not any("hook" in nid for nid in upserted_ids)


@requires_tree_sitter
@pytest.mark.asyncio
async def test_index_directory_skips_node_modules(tmp_path):
    """index_directory skips node_modules entirely."""
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_bytes(b"function x(){}")
    (tmp_path / "app.py").write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.success > 0
    upserted_ids = [
        call_args[1]["ids"][0]
        for call_args in indexer._collection.upsert.call_args_list
    ]
    assert not any("index" in nid and "node_modules" in str(nid) for nid in upserted_ids)


@pytest.mark.asyncio
async def test_index_directory_unsupported_extension_skipped(tmp_path):
    """index_directory skips files with unsupported extensions."""
    (tmp_path / "config.yaml").write_bytes(b"key: value\n")
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.success == 0
    assert result.skipped == 0  # skipped only counts supported-but-hash-match; unsupported = 0
    assert not indexer._collection.upsert.called
