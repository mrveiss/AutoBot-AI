# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
    find_callers,
)

SIMPLE_PYTHON = b"""
def greet(name: str) -> str:
    return "hello " + name

class Greeter:
    def run(self) -> None:
        greet("world")
"""


def _all_upserted(indexer: CodeIndexer) -> list[tuple[str, dict]]:
    """Flatten every (id, metadata) pair upserted on a MagicMock collection."""
    pairs: list[tuple[str, dict]] = []
    for call_args in indexer._collection.upsert.call_args_list:
        pairs.extend(zip(call_args[1]["ids"], call_args[1]["metadatas"]))
    return pairs


def _find_edge(indexer: CodeIndexer, source_id: str, target_name: str) -> dict | None:
    for _nid, meta in _all_upserted(indexer):
        is_match = meta.get("source_id") == source_id and meta.get("target_name") == target_name
        if meta.get("record_type") == "edge" and is_match:
            return meta
    return None


def test_make_node_id_is_stable_and_dotted() -> None:
    """#13470: the canonical identity is the dotted module-path scheme, not the
    old lowercase '<stem>::<name>' one — that scheme collided whenever two
    files shared a basename (see autobot_shared/code_graph/identity_test.py)."""
    nid = _make_node_id("MyFunc", "src.auth")
    assert nid == "src.auth.MyFunc"
    assert nid == _make_node_id("MyFunc", "src.auth")


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

    # #4912: index_code now enqueues a background task and returns immediately.
    assert response["status"] == "queued"
    assert response["task_id"]


@requires_tree_sitter
@pytest.mark.asyncio
async def test_class_method_call_graph(tmp_path) -> None:
    """Class method node id includes the class (#4908); its outgoing call is
    persisted as a resolved edge document pointing at the sibling method (#13469).

    Regression test for a pre-existing bug this PR fixes as a side effect of
    the resolver rework: the call-graph pass never tracked class scope, so a
    method's structural-pass id and its own call-graph scope disagreed and
    its calls never attached to it at all — this test failed on
    origin/Dev_new_gui before this PR (`run`'s calls metadata was `''`, see
    the PR description for the captured before/after run)."""
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

    upserted_ids = [nid for nid, _meta in _all_upserted(indexer)]
    assert "mymod.MyClass.run" in upserted_ids, f"Expected 'mymod.MyClass.run' in upserted IDs, got: {upserted_ids}"
    assert "mymod.MyClass.helper" in upserted_ids

    edge = _find_edge(indexer, source_id="mymod.MyClass.run", target_name="helper")
    assert edge is not None, f"Expected an edge run->helper, got ids: {upserted_ids}"
    assert edge["target_id"] == "mymod.MyClass.helper"
    assert edge["origin"] == "extracted"
    assert edge["resolved"] is True


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

    # #4912: index_code now enqueues a background task and returns immediately.
    assert response["status"] == "queued"
    assert response["task_id"]


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


# ---------------------------------------------------------------------------
# Honest provenance — ambiguous and unresolved callees (#13469, #13482 Q2)
# ---------------------------------------------------------------------------


@requires_tree_sitter
@pytest.mark.asyncio
async def test_ambiguous_and_unresolved_calls_recorded_honestly(tmp_path) -> None:
    """A callee matching two candidates is "ambiguous", not silently dropped
    or mislabelled "extracted"; a callee matching none is "inferred" with
    target_id="" and resolved=False, never invented."""
    (tmp_path / "a_one.py").write_bytes(b"def process() -> None:\n    pass\n")
    (tmp_path / "a_two.py").write_bytes(b"def process() -> None:\n    pass\n")
    (tmp_path / "b_caller.py").write_bytes(
        b"def caller() -> None:\n    process()\n    totally_unknown_function()\n"
    )
    indexer = _make_indexer(tmp_path)
    result = await indexer.index_directory(str(tmp_path))
    assert result.failed == 0

    ambiguous = _find_edge(indexer, source_id="b_caller.caller", target_name="process")
    assert ambiguous is not None
    assert ambiguous["origin"] == "ambiguous"
    assert ambiguous["target_id"] == ""
    assert ambiguous["resolved"] is False
    assert ambiguous["candidate_count"] == 2

    unresolved = _find_edge(indexer, source_id="b_caller.caller", target_name="totally_unknown_function")
    assert unresolved is not None
    assert unresolved["origin"] == "inferred"
    assert unresolved["target_id"] == ""
    assert unresolved["resolved"] is False
    assert unresolved["candidate_count"] == 0


# ---------------------------------------------------------------------------
# Traversal — "who calls X" (#13469; the umbrella #13467 says this capability
# does not exist today because the old `calls` CSV had no readers)
# ---------------------------------------------------------------------------


class _FakeCollection:
    """Minimal in-memory ChromaDB-collection stand-in with *real* upsert/get(where=)
    semantics, supporting exactly the query shapes this module issues
    (plain equality and ``$and``/``$eq``).

    ``autobot-backend/conftest.py`` stubs the real ``chromadb`` package for
    this entire test suite with a MagicMock (#MVA-1119 — the real client
    hangs at import time without a local Chroma server), so a test wanting
    real query *behaviour* rather than a mock that only records calls needs
    its own minimal implementation. This is not a duplicate ChromaDB client —
    it implements only the two operations CodeIndexer/find_callers use.
    """

    def __init__(self) -> None:
        self._records: dict[str, dict] = {}

    def upsert(self, ids: list[str], embeddings: list, documents: list[str], metadatas: list[dict]) -> None:
        for nid, meta in zip(ids, metadatas):
            self._records[nid] = meta

    def get(self, where: dict | None = None, include: list[str] | None = None) -> dict:
        matched = [meta for meta in self._records.values() if _fake_where_matches(meta, where)]
        return {"ids": list(self._records.keys()), "metadatas": matched}


def _fake_where_matches(meta: dict, where: dict | None) -> bool:
    if not where:
        return True
    if "$and" in where:
        return all(_fake_where_matches(meta, clause) for clause in where["$and"])
    return all(meta.get(key) == (val["$eq"] if isinstance(val, dict) else val) for key, val in where.items())


@requires_tree_sitter
@pytest.mark.asyncio
async def test_find_callers_traversal(tmp_path) -> None:
    """Given an indexed fixture repo, find_callers() answers "who calls helper"
    with an exact metadata lookup against the persisted edge documents — the
    traversal capability #13467 says does not exist today because the old
    `calls` CSV field had no readers."""
    collection = _FakeCollection()
    embed_model = MagicMock()
    embed_model.get_text_embedding = MagicMock(side_effect=lambda text: [float(len(text) % 7)] * 4)
    indexer = CodeIndexer(collection=collection, embed_model=embed_model, cache_file=tmp_path / ".cache.json")

    (tmp_path / "helpers.py").write_bytes(b"def helper() -> None:\n    pass\n")
    (tmp_path / "service_a.py").write_bytes(b"def run_a() -> None:\n    helper()\n")
    (tmp_path / "service_b.py").write_bytes(b"def run_b() -> None:\n    helper()\n")
    (tmp_path / "service_c.py").write_bytes(b"def run_c() -> None:\n    pass\n")

    result = await indexer.index_directory(str(tmp_path))
    assert result.failed == 0

    callers = await find_callers(collection, target_id="helpers.helper")
    caller_ids = {edge["source_id"] for edge in callers}
    assert caller_ids == {"service_a.run_a", "service_b.run_b"}
    assert all(edge["origin"] in ("extracted", "inferred") for edge in callers)


@requires_tree_sitter
@pytest.mark.asyncio
async def test_known_ids_seeded_across_reindex_runs(tmp_path) -> None:
    """A second index_directory() run (simulating a later incremental reindex)
    still resolves a cross-file call even though the callee's file is
    unchanged and therefore skipped by the hash cache (#13469) — without
    seeding known ids from the collection, this would regress to "unresolved"
    every run after the first."""
    collection = _FakeCollection()
    embed_model = MagicMock()
    embed_model.get_text_embedding = MagicMock(side_effect=lambda text: [float(len(text) % 7)] * 4)

    (tmp_path / "helpers.py").write_bytes(b"def helper() -> None:\n    pass\n")
    (tmp_path / "service_a.py").write_bytes(b"def run_a() -> None:\n    helper()\n")

    first_indexer = CodeIndexer(collection=collection, embed_model=embed_model, cache_file=tmp_path / ".cache.json")
    await first_indexer.index_directory(str(tmp_path))

    # New file added; helpers.py/service_a.py are unchanged and will be
    # skipped by the hash cache on this second, independent CodeIndexer run.
    (tmp_path / "service_c.py").write_bytes(b"def run_c() -> None:\n    helper()\n")
    second_indexer = CodeIndexer(collection=collection, embed_model=embed_model, cache_file=tmp_path / ".cache.json")
    result = await second_indexer.index_directory(str(tmp_path))
    assert result.failed == 0

    callers = await find_callers(collection, target_id="helpers.helper")
    caller_ids = {edge["source_id"] for edge in callers}
    assert "service_c.run_c" in caller_ids
