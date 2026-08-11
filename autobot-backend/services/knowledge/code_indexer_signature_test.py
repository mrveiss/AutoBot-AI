# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Formatting churn must not re-embed a file (#13509).

`CodeIndexer` invalidated on a whole-file content hash, so a reformat cost the
same as a rewrite — and the PostToolUse hook reformats every `.py` we touch.
The second-stage signature check is meant to make that free.

These tests count **embedding calls**, because that is the actual cost and the
only thing that proves the saving. Asserting "skipped" counters would pass on an
implementation that skipped the work and re-embedded anyway.

The other half is the danger: a file whose interface changed must still be
re-embedded, and every failure path must fall through to full re-analysis.
Serving a stale graph is worse than paying for a rebuild.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("tree_sitter_python", reason="tree-sitter is required to extract Python nodes")

from services.knowledge.code_indexer import CodeIndexer  # noqa: E402

ORIGINAL = """
import os


def fetch(user_id: int) -> str:
    value = os.getenv("X")
    return value


class Service:
    def run(self) -> bool:
        return True
"""


class _CountingEmbedder:
    def __init__(self):
        self.calls = 0

    def get_text_embedding(self, _text):
        self.calls += 1
        return [0.0, 0.1, 0.2]


def _indexer(tmp_path: Path):
    embedder = _CountingEmbedder()
    collection = MagicMock()
    collection.get.return_value = {"ids": [], "metadatas": []}
    idx = CodeIndexer(
        collection=collection,
        embed_model=embedder,
        cache_file=tmp_path / "cache.json",
    )
    return idx, embedder, collection


def _write(tmp_path: Path, src: str) -> str:
    f = tmp_path / "sample.py"
    f.write_text(src, encoding="utf-8")
    return str(f)


def _index(idx, path, root):
    return asyncio.run(idx.index_file(path, str(root)))


class TestFormattingChurnIsFree:
    def test_reformatting_performs_zero_embedding_calls(self, tmp_path):
        """AC: a no-semantic-change edit must not re-embed."""
        path = _write(tmp_path, ORIGINAL)
        idx, embedder, _ = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls
        assert after_first > 0, "the first index must embed something"

        # A comment and a blank line: bytes differ, interface does not.
        _write(tmp_path, ORIGINAL.replace("    value = os.getenv", "    # reformatted\n    value = os.getenv"))
        _index(idx, path, tmp_path)

        assert embedder.calls == after_first, "reformatting must cost no embeddings"

    def test_a_body_rewrite_performs_zero_embedding_calls_but_updates_line_ranges(self, tmp_path):
        """AC: body-only edits refresh line ranges without re-embedding."""
        path = _write(tmp_path, ORIGINAL)
        idx, embedder, collection = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls
        collection.update.reset_mock()

        _write(
            tmp_path,
            ORIGINAL.replace('    value = os.getenv("X")\n    return value', '    return os.getenv("X") or ""'),
        )
        _index(idx, path, tmp_path)

        assert embedder.calls == after_first, "a body rewrite must cost no embeddings"
        assert collection.update.called, "line ranges must still be refreshed, or go-to-definition drifts"


class TestInterfaceChangesStillRebuild:
    @pytest.mark.parametrize(
        "mutation",
        [
            ("def fetch(user_id: int) -> str:", "def fetch(user_id: int, force: bool) -> str:"),
            ("def fetch(", "def fetch_all("),
            ("import os", "import os\nimport sys"),
            ("    def run(self) -> bool:", "    def run(self, mode: str) -> bool:"),
        ],
        ids=["added-param", "renamed", "added-import", "method-signature"],
    )
    def test_an_interface_change_re_embeds(self, tmp_path, mutation):
        path = _write(tmp_path, ORIGINAL)
        idx, embedder, _ = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls

        _write(tmp_path, ORIGINAL.replace(*mutation))
        _index(idx, path, tmp_path)

        assert embedder.calls > after_first, f"{mutation[0]!r} changed the interface and must re-embed"


class TestFailsOpen:
    def test_a_file_with_no_computable_signature_always_re_embeds(self, tmp_path):
        """Non-Python keeps today's behaviour rather than skipping on a fingerprint it never had."""
        idx, embedder, _ = _indexer(tmp_path)
        f = tmp_path / "sample.js"
        f.write_text("function a(){ return 1 }\n", encoding="utf-8")
        _index(idx, str(f), tmp_path)
        after_first = embedder.calls

        f.write_text("function a(){ return 1 }\n// touched\n", encoding="utf-8")
        _index(idx, str(f), tmp_path)

        assert embedder.calls > after_first, "no signature must mean full re-analysis"

    def test_a_non_python_extension_never_gets_a_signature(self):
        """The extension guard, not the parse failure, is what must reject non-Python.

        The behavioural test above passes either way: its JS fixture is not valid
        Python, so `ast.parse` raises and the fail-open path already re-embeds.
        Deleting the `.py` check therefore survived it. This is the case that
        separates them — JS that also parses as Python. Without the guard it
        gets a fingerprint derived from *Python* semantics, and a genuine JS
        change that Python's AST cannot see would be skipped as "unchanged".
        """
        source = b"config = {}\n"

        assert CodeIndexer._signature_of(".js", source) is None
        assert isinstance(CodeIndexer._signature_of(".py", source), str), "identical bytes, .py: fingerprinted"

    def test_force_re_indexes_even_when_the_signature_is_identical(self, tmp_path):
        """`force=True` means rebuild — the fast path must not quietly outrank it.

        force exists for corruption recovery and extractor upgrades, where the
        stored fingerprint is exactly what must not be trusted.
        """
        path = _write(tmp_path, ORIGINAL)
        idx, embedder, _ = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls

        asyncio.run(idx.index_file(path, str(tmp_path), force=True))

        assert embedder.calls > after_first, "force must re-embed regardless of the signature"

    def test_a_failed_line_refresh_clears_the_stored_signature(self, tmp_path):
        """A refresh that fails must not leave the cache claiming the file is current."""
        path = _write(tmp_path, ORIGINAL)
        idx, _, collection = _indexer(tmp_path)
        _index(idx, path, tmp_path)

        collection.update.side_effect = RuntimeError("chroma down")
        _write(tmp_path, ORIGINAL.replace("    return value", "    return value  # touched"))
        _index(idx, path, tmp_path)

        from services.knowledge.code_indexer import _SIGNATURE_KEY_PREFIX

        rel = str(Path(path).relative_to(tmp_path))
        assert _SIGNATURE_KEY_PREFIX + rel not in idx._hash_cache, "a failed refresh must force a rebuild next run"

    def test_unchanged_content_still_short_circuits_before_any_work(self, tmp_path):
        """The existing content-hash skip must survive this change."""
        path = _write(tmp_path, ORIGINAL)
        idx, embedder, _ = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls

        result = _index(idx, path, tmp_path)

        assert embedder.calls == after_first
        assert result.skipped == 1
