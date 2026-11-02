# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Codebase-analytics panels must tell failed, not-indexed and empty apart (#17651).

Store-level: the collections are the repo's in-memory backend, which evaluates
``where`` filters with ChromaDB semantics, so the filters the endpoints build are
evaluated by a store rather than asserted on a mock. (``chromadb`` itself is
stubbed out under the unit-test conftest.)
"""

import itertools
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.codebase_analytics import storage as analytics_storage
from api.codebase_analytics.endpoints import declarations as decl_mod
from api.codebase_analytics.endpoints import stats as stats_mod
from api.codebase_analytics.endpoints.store_state import index_state, source_is_indexed
from autobot_shared.status_enums import Severity
from knowledge.backends.memory_adapter import InMemoryClient

_names = itertools.count()
_CLIENT = InMemoryClient()  # ChromaDB where-semantics (knowledge.backends.where_filter)


def _collection(rows: list[dict]):
    col = _CLIENT.get_or_create_collection(f"t17651-{next(_names)}")
    if rows:
        col.add(
            ids=[f"id{i}" for i in range(len(rows))],
            documents=["x"] * len(rows),
            metadatas=rows,
        )
    return col


FUNC = {"type": "function", "name": "f", "file_path": "a.py", "start_line": "3", "source_id": "s1"}
PROBLEM = {
    "type": "problem",
    "problem_type": "p",
    "severity": Severity.LOW.value,
    "file_path": "a.py",
    "source_id": "s1",
}


class _Broken:
    def get(self, **_kwargs):
        raise RuntimeError("chroma down")


def test_empty_store_is_not_indexed():
    assert index_state(_collection([]), "s1", False) == {
        "status": "no_data",
        "indexed": False,
        "message": "This source has not been indexed yet. Run indexing first.",
    }


def test_other_sources_rows_do_not_make_this_source_indexed():
    assert source_is_indexed(_collection([FUNC]), "s2") is False


def test_any_row_type_counts_as_indexed():
    assert index_state(_collection([PROBLEM]), "s1", False) == {"status": "success", "indexed": True}


def test_a_store_read_failure_is_not_read_as_not_indexed():
    with pytest.raises(RuntimeError):
        source_is_indexed(_Broken(), "s1")


@pytest.mark.asyncio
async def test_declarations_unopenable_store_is_503_not_an_empty_list():
    with patch.object(decl_mod, "get_code_collection", return_value=None):
        with pytest.raises(HTTPException) as exc:
            await decl_mod.get_code_declarations(source_id="s1")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_declarations_store_read_error_is_503_not_success():
    with patch.object(decl_mod, "get_code_collection", return_value=_Broken()):
        with pytest.raises(HTTPException) as exc:
            await decl_mod.get_code_declarations(source_id="s1")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_declarations_three_answers_are_distinct():
    async def ask(rows):
        with patch.object(decl_mod, "get_code_collection", return_value=_collection(rows)):
            return (await decl_mod.get_code_declarations(source_id="s1")).body

    import json

    not_indexed = json.loads(await ask([]))
    indexed_none = json.loads(await ask([PROBLEM]))
    found = json.loads(await ask([FUNC, PROBLEM]))
    assert (not_indexed["status"], not_indexed["indexed"], not_indexed["declarations"]) == ("no_data", False, [])
    assert (indexed_none["status"], indexed_none["indexed"], indexed_none["declarations"]) == ("success", True, [])
    assert (found["status"], found["indexed"], found["total_count"]) == ("success", True, 1)


async def _problems(collection, **kwargs):
    with (
        patch.object(stats_mod, "get_code_collection", return_value=collection),
        patch.object(stats_mod, "resolve_source_root", new=AsyncMock(return_value=None)),
        patch.object(stats_mod, "filter_problems_by_file_existence", side_effect=lambda p, _r: p),
        patch.object(stats_mod, "resolve_git_repo_root", return_value="."),
    ):
        return await stats_mod.get_codebase_problems(source_id="s1", **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", [None, _Broken()])
async def test_problems_unreadable_store_is_503_not_no_data(collection):
    with pytest.raises(HTTPException) as exc:
        await _problems(collection)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_problems_indexed_with_none_found_differs_from_not_indexed():
    import json

    empty = json.loads((await _problems(_collection([]))).body)
    functions_only = json.loads((await _problems(_collection([FUNC]))).body)
    found = json.loads((await _problems(_collection([PROBLEM]))).body)
    assert (empty["status"], empty["indexed"]) == ("no_data", False)
    assert (functions_only["status"], functions_only["indexed"], functions_only["problems"]) == ("success", True, [])
    assert (found["status"], found["indexed"], found["total_count"]) == ("success", True, 1)


def _opened_path(module, opener, tmp_path):
    """The ``db_path`` the module hands its client, with the shared helper pointed at tmp_path."""
    seen = {}

    def fake_client(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop")

    with (
        patch.object(module, "chromadb_data_dir", return_value=tmp_path / "store"),
        patch.object(module, "get_default_client", side_effect=fake_client),
    ):
        opener()
    return seen.get("db_path")


def test_analytics_store_path_comes_from_the_one_helper(tmp_path):
    """The path is the shared helper's, not a second spelling (#18143, #17651)."""
    assert _opened_path(analytics_storage, analytics_storage.get_code_collection, tmp_path) == str(tmp_path / "store")


def test_no_analytics_module_spells_the_store_path_itself():
    backend = Path(__file__).resolve().parents[3]
    files = [
        backend / "api/codebase_analytics/storage.py",
        backend / "api/codebase_analytics/chromadb_storage.py",
        backend / "code_intelligence/pattern_analysis/storage.py",
    ]
    offenders = [str(f.name) for f in files if '"data" / "chromadb"' in f.read_text(encoding="utf-8")]
    # pattern_analysis is stubbed by the unit conftest, so its path is pinned by source, not by call.
    assert offenders == []
    assert "chromadb_data_dir()" in files[2].read_text(encoding="utf-8")
    assert "chromadb_data_dir" in files[1].read_text(encoding="utf-8")
