# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

requires_tree_sitter = pytest.mark.skipif(not tree_sitter_available, reason="tree-sitter-python not installed")

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


def test_make_node_id_is_stable_and_lowercase() -> None:
    nid = _make_node_id("MyFunc", "src/auth.py")
    assert nid == "auth::myfunc"
    assert nid == _make_node_id("MyFunc", "src/auth.py")


@requires_tree_sitter
def test_extract_python_finds_function_nodes() -> None:
    result = extract_python("module.py", SIMPLE_PYTHON)
    node_names = [n["name"] for n in result["nodes"]]
    assert "greet" in node_names


@requires_tree_sitter
def test_extract_python_finds_class_nodes() -> None:
    result = extract_python("module.py", SIMPLE_PYTHON)
    node_names = [n["name"] for n in result["nodes"]]
    assert "Greeter" in node_names


@requires_tree_sitter
def test_extract_python_finds_call_edge() -> None:
    result = extract_python("module.py", SIMPLE_PYTHON)
    edge_pairs = [(e["source"], e["target_name"]) for e in result["edges"]]
    assert any(target == "greet" for _, target in edge_pairs)


@requires_tree_sitter
def test_extract_python_no_duplicate_edges() -> None:
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
async def test_index_python_file_upserts_nodes(tmp_path) -> None:
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_file(str(src), root_dir=str(tmp_path))
    assert result.success > 0
    assert indexer._collection.upsert.called


@requires_tree_sitter
async def test_index_unchanged_file_skips(tmp_path) -> None:
    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    await indexer.index_file(str(src), root_dir=str(tmp_path))
    call_count_first = indexer._collection.upsert.call_count

    result = await indexer.index_file(str(src), root_dir=str(tmp_path))
    assert result.skipped == 1
    assert indexer._collection.upsert.call_count == call_count_first


@requires_tree_sitter
async def test_force_reindex_bypasses_cache(tmp_path) -> None:
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
async def test_index_directory_indexes_all_py_files(tmp_path) -> None:
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
async def test_index_directory_skips_hidden_dirs(tmp_path) -> None:
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
    upserted_ids = [call_args[1]["ids"][0] for call_args in indexer._collection.upsert.call_args_list]
    assert not any("hook" in nid for nid in upserted_ids)


@requires_tree_sitter
@pytest.mark.asyncio
async def test_index_directory_skips_node_modules(tmp_path) -> None:
    """index_directory skips node_modules entirely."""
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_bytes(b"function x(){}")
    (tmp_path / "app.py").write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.success > 0
    upserted_ids = [call_args[1]["ids"][0] for call_args in indexer._collection.upsert.call_args_list]
    assert not any("index" in nid and "node_modules" in str(nid) for nid in upserted_ids)


@pytest.mark.asyncio
async def test_index_directory_unsupported_extension_skipped(tmp_path) -> None:
    """index_directory skips files with unsupported extensions."""
    (tmp_path / "config.yaml").write_bytes(b"key: value\n")
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.success == 0
    assert result.skipped == 0  # skipped only counts supported-but-hash-match; unsupported = 0
    assert not indexer._collection.upsert.called


# ---------------------------------------------------------------------------
# Concurrent index_directory — hash cache write-race regression (#4895)
# ---------------------------------------------------------------------------


@requires_tree_sitter
@pytest.mark.asyncio
async def test_concurrent_index_directory_preserves_all_cache_entries(tmp_path) -> None:
    """Two concurrent index_directory() calls on disjoint file sets must both
    have their cache entries persisted — neither must overwrite the other."""
    import asyncio
    import json as _json

    # Two source directories, each with one .py file
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "alpha.py").write_bytes(b"def alpha(): pass\n")
    (dir_b / "beta.py").write_bytes(b"def beta(): pass\n")

    # Both indexers share the same cache file (mirrors production behaviour).
    cache_file = tmp_path / ".code_index_hashes.json"

    # Clear any stale process-level lock for this cache path before the test.
    import services.knowledge.code_indexer as _ci_mod

    _ci_mod._CACHE_FILE_LOCKS.pop(str(cache_file), None)

    indexer_a = CodeIndexer(
        collection=MagicMock(upsert=MagicMock()),
        embed_model=MagicMock(get_text_embedding=MagicMock(return_value=[0.1] * 384)),
        cache_file=cache_file,
    )
    indexer_b = CodeIndexer(
        collection=MagicMock(upsert=MagicMock()),
        embed_model=MagicMock(get_text_embedding=MagicMock(return_value=[0.1] * 384)),
        cache_file=cache_file,
    )

    # Run both concurrently — the lock must serialise the load+index+save cycle.
    await asyncio.gather(
        indexer_a.index_directory(str(dir_a)),
        indexer_b.index_directory(str(dir_b)),
    )

    cache = _json.loads(cache_file.read_text(encoding="utf-8"))
    # Both files must appear in the final cache.
    assert any("alpha" in k for k in cache), f"alpha.py missing from cache: {cache}"
    assert any("beta" in k for k in cache), f"beta.py missing from cache: {cache}"


# ---------------------------------------------------------------------------
# index_code endpoint — path traversal validation (#4894)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_code_rejects_out_of_root_path(tmp_path) -> None:
    """POST /index/code must return 400 when root_dir is outside PROJECT_ROOT."""
    from unittest.mock import patch

    import pytest
    from fastapi import HTTPException

    from api.knowledge_population import index_code

    with patch("constants.path_constants.PATH") as mock_path:
        mock_path.PROJECT_ROOT = str(tmp_path / "project")
        with pytest.raises(HTTPException) as exc_info:
            await index_code({"root_dir": "/etc"})
    assert exc_info.value.status_code == 400
    assert "project root" in exc_info.value.detail


@pytest.mark.asyncio
async def test_index_code_rejects_prefix_confusion_path(tmp_path) -> None:
    """root_dir=/tmp/projectroot_evil must not match /tmp/projectroot."""
    from unittest.mock import patch

    import pytest
    from fastapi import HTTPException

    from api.knowledge_population import index_code

    project = tmp_path / "projectroot"
    evil = tmp_path / "projectroot_evil"

    with patch("constants.path_constants.PATH") as mock_path:
        mock_path.PROJECT_ROOT = str(project)
        with pytest.raises(HTTPException) as exc_info:
            await index_code({"root_dir": str(evil)})
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_index_code_accepts_project_root_itself(tmp_path) -> None:
    """root_dir equal to PROJECT_ROOT is allowed and proceeds to indexing."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from api.knowledge_population import index_code

    project = tmp_path / "project"
    project.mkdir()

    mock_result = MagicMock(success=0, failed=0, skipped=0, errors=[])
    mock_indexer = MagicMock()
    mock_indexer.index_directory = AsyncMock(return_value=mock_result)

    mock_doc_svc = MagicMock()
    mock_doc_svc.initialize = AsyncMock(return_value=True)
    mock_doc_svc._collection = MagicMock()
    mock_doc_svc._embed_model = MagicMock()

    with (
        patch("constants.path_constants.PATH") as mock_path,
        patch("services.knowledge.doc_indexer.get_doc_indexer_service", return_value=mock_doc_svc),
        patch("services.knowledge.code_indexer.CodeIndexer", return_value=mock_indexer),
    ):
        mock_path.PROJECT_ROOT = str(project)
        response = await index_code({"root_dir": str(project)})

    assert response["status"] == "ok"


@requires_tree_sitter
@pytest.mark.asyncio
async def test_class_method_call_graph(tmp_path) -> None:
    """Class method node ID uses parent prefix; calls metadata is non-empty (#4908)."""
    src = tmp_path / "mymod.py"
    src.write_bytes(b"""
class MyClass:
    def helper(self) -> None:
        pass

    def run(self) -> None:
        self.helper()
""")
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_file(str(src), root_dir=str(tmp_path))
    assert result.success > 0

    # Verify method node ID includes class parent prefix
    upserted_ids = [call_args[1]["ids"][0] for call_args in indexer._collection.upsert.call_args_list]
    assert "mymod::myclass__run" in upserted_ids, f"Expected 'mymod::myclass__run' in upserted IDs, got: {upserted_ids}"

    # Verify the `calls` metadata on `run` is non-empty
    run_calls = None
    for call_args in indexer._collection.upsert.call_args_list:
        if call_args[1]["ids"][0] == "mymod::myclass__run":
            run_calls = call_args[1]["metadatas"][0]["calls"]
            break
    assert run_calls, f"Expected non-empty 'calls' metadata for mymod::myclass__run, got: {run_calls!r}"


@pytest.mark.asyncio
async def test_index_code_accepts_subdir_of_project_root(tmp_path) -> None:
    """root_dir within PROJECT_ROOT is allowed and proceeds to indexing."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from api.knowledge_population import index_code

    project = tmp_path / "project"
    subdir = project / "autobot-backend" / "services"
    subdir.mkdir(parents=True)

    mock_result = MagicMock(success=0, failed=0, skipped=0, errors=[])
    mock_indexer = MagicMock()
    mock_indexer.index_directory = AsyncMock(return_value=mock_result)

    mock_doc_svc = MagicMock()
    mock_doc_svc.initialize = AsyncMock(return_value=True)
    mock_doc_svc._collection = MagicMock()
    mock_doc_svc._embed_model = MagicMock()

    with (
        patch("constants.path_constants.PATH") as mock_path,
        patch("services.knowledge.doc_indexer.get_doc_indexer_service", return_value=mock_doc_svc),
        patch("services.knowledge.code_indexer.CodeIndexer", return_value=mock_indexer),
    ):
        mock_path.PROJECT_ROOT = str(project)
        response = await index_code({"root_dir": str(subdir)})

    assert response["status"] == "ok"


# ---------------------------------------------------------------------------
# dep_error propagation — missing tree-sitter counted as failed (#4938)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_index_file_dep_error_counts_as_failed(tmp_path) -> None:
    """When an extractor returns dep_error, index_file must record failed=1 not skipped=1."""
    import services.knowledge.code_indexer as _ci_mod

    src = tmp_path / "module.py"
    src.write_bytes(SIMPLE_PYTHON)
    indexer = _make_indexer(tmp_path)

    dep_error_result = {"nodes": [], "edges": [], "dep_error": "tree-sitter-python not installed"}
    original = _ci_mod._EXTRACTORS[".py"]
    try:
        _ci_mod._EXTRACTORS[".py"] = lambda path, content: dep_error_result
        result = await indexer.index_file(str(src), root_dir=str(tmp_path))
    finally:
        _ci_mod._EXTRACTORS[".py"] = original

    assert result.failed == 1
    assert result.skipped == 0
    assert result.success == 0
    assert any("missing dependency" in e for e in result.errors)
    assert any("tree-sitter-python" in e for e in result.errors)
