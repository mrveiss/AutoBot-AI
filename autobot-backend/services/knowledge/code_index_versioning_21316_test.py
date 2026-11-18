# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21316: the code-index cache version includes the installed tree-sitter and grammar versions.

``importlib.metadata.version`` is faked, so a "grammar upgrade" is a one-line change in the
fake. Pre-fix, the cache version was ``EXTRACTOR_VERSION`` alone: every ``== {}`` assertion on
a changed grammar below failed (the cache was still hit), and ``GraphProvenance`` had no
``grammar_versions`` field.
"""

import asyncio
import json
from importlib import metadata
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from services.knowledge import code_index_versioning as versioning
from services.knowledge.code_indexer import (
    _CACHE_VERSION_KEY,
    EXTRACTOR_VERSION,
    CodeIndexer,
    CodeIndexResult,
    GraphProvenance,
)

_BASE = {"tree-sitter": "0.25.0", "tree-sitter-python": "0.25.1", "tree-sitter-javascript": "0.25.2"}


@pytest.fixture
def grammar_versions_env(monkeypatch):
    """Mutable fake of the installed distributions; mutate the dict to 'upgrade' a package."""
    versions = dict(_BASE)

    def fake_version(name: str) -> str:
        if name not in versions:
            raise metadata.PackageNotFoundError(name)
        return versions[name]

    monkeypatch.setattr(metadata, "version", fake_version)
    return versions


def _indexer(cache_file: Path) -> CodeIndexer:
    return CodeIndexer(collection=MagicMock(), embed_model=MagicMock(), cache_file=cache_file)


def test_every_package_the_indexer_loads_is_a_reported_grammar() -> None:
    assert set(versioning.GRAMMAR_PACKAGES) == {"tree-sitter", "tree-sitter-python", "tree-sitter-javascript"}


def test_an_unchanged_environment_still_hits_the_cache(grammar_versions_env, tmp_path) -> None:
    cache = tmp_path / "hashes.json"
    first = _indexer(cache)
    first._hash_cache = {"a.py": "hash-a"}
    first._save_cache()

    assert _indexer(cache)._hash_cache == {"a.py": "hash-a"}


@pytest.mark.parametrize("package", sorted(_BASE))
def test_changing_a_reported_version_invalidates_cached_entries(grammar_versions_env, tmp_path, package) -> None:
    cache = tmp_path / "hashes.json"
    first = _indexer(cache)
    first._hash_cache = {"a.py": "hash-a"}
    first._save_cache()

    grammar_versions_env[package] = "9.9.9"

    assert _indexer(cache)._hash_cache == {}


def test_the_cache_version_is_one_value_under_the_existing_key(grammar_versions_env, tmp_path) -> None:
    cache = tmp_path / "hashes.json"
    indexer = _indexer(cache)
    indexer._save_cache()
    written = json.loads(cache.read_text(encoding="utf-8"))

    assert [k for k in written if k.startswith("::") and "version" in k] == [_CACHE_VERSION_KEY]
    assert written[_CACHE_VERSION_KEY].startswith(f"{EXTRACTOR_VERSION}|")
    assert "0.25.1" in written[_CACHE_VERSION_KEY]


def test_a_missing_grammar_is_reported_not_raised(grammar_versions_env) -> None:
    del grammar_versions_env["tree-sitter-javascript"]

    assert versioning.installed_grammar_versions()["tree-sitter-javascript"] == versioning.NOT_INSTALLED


def test_the_provenance_record_carries_the_grammar_versions_that_wrote_the_graph(
    grammar_versions_env, tmp_path
) -> None:
    collection = MagicMock()
    collection.get.return_value = {"ids": [], "metadatas": []}
    embed = MagicMock()
    embed.get_text_embedding.return_value = [0.1, 0.2]
    indexer = CodeIndexer(collection=collection, embed_model=embed, cache_file=tmp_path / "hashes.json")

    asyncio.run(indexer._write_provenance(str(tmp_path), CodeIndexResult()))

    written = collection.upsert.call_args.kwargs["metadatas"][0]
    assert json.loads(written["grammar_versions"]) == _BASE


def test_a_graph_written_by_other_grammars_is_not_current(grammar_versions_env) -> None:
    record = GraphProvenance(extractor_version=EXTRACTOR_VERSION, grammar_versions=versioning.grammar_versions_json())
    assert record.is_current_extractor

    grammar_versions_env["tree-sitter-python"] = "9.9.9"

    assert not record.is_current_extractor
