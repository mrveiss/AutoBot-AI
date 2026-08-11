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


class _FakeCollection:
    """A collection that actually stores records.

    A MagicMock cannot answer these tests: the skip path checks whether the ids
    it is about to patch exist, and ChromaDB's ``update`` silently drops unknown
    ids. Against a mock, "record present" and "record missing" look identical,
    which is precisely the confusion the guard exists to remove.
    """

    def __init__(self):
        self.records: dict[str, tuple] = {}
        self.update_calls: list[dict] = []
        self.update_side_effect: Exception | None = None
        self.refuse_upsert_ids: set[str] = set()

    def upsert(self, ids, embeddings=None, documents=None, metadatas=None):
        for idx, rid in enumerate(ids):
            if rid in self.refuse_upsert_ids:
                raise RuntimeError(f"simulated upsert failure for {rid}")
            document = documents[idx] if documents else None
            metadata = metadatas[idx] if metadatas else {}
            self.records[rid] = (document, metadata)

    def update(self, ids, documents=None, metadatas=None, **_kwargs):
        if self.update_side_effect:
            raise self.update_side_effect
        self.update_calls.append({"ids": list(ids), "documents": documents, "metadatas": metadatas})
        for idx, rid in enumerate(ids):
            if rid not in self.records:
                continue  # ChromaDB drops unknown ids silently — so do we
            document, metadata = self.records[rid]
            new_meta = {**(metadata or {}), **(metadatas[idx] if metadatas else {})}
            self.records[rid] = (documents[idx] if documents else document, new_meta)

    def get(self, ids=None, where=None, include=None):
        if ids is not None:
            present = [rid for rid in ids if rid in self.records]
            return {"ids": present, "metadatas": [self.records[rid][1] for rid in present]}
        wanted = (where or {}).get("record_type", {}).get("$eq") if where else None
        matched = [
            rid
            for rid, (_doc, meta) in self.records.items()
            if wanted is None or (meta or {}).get("record_type") == wanted
        ]
        return {"ids": matched, "metadatas": [self.records[rid][1] for rid in matched]}

    def metadata_of(self, record_id: str) -> dict:
        return self.records[record_id][1]

    def document_of(self, record_id: str) -> str:
        return self.records[record_id][0]


def _indexer(tmp_path: Path):
    embedder = _CountingEmbedder()
    collection = _FakeCollection()
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
        collection.update_calls.clear()

        _write(
            tmp_path,
            ORIGINAL.replace('    value = os.getenv("X")\n    return value', '    return os.getenv("X") or ""'),
        )
        _index(idx, path, tmp_path)

        assert embedder.calls == after_first, "a body rewrite must cost no embeddings"
        assert collection.update_calls, "line ranges must still be refreshed, or go-to-definition drifts"


class TestTheRefreshPathKeepsRecordsConsistent:
    """Skipping the embedding must not leave any part of the record behind.

    The saving is only sound if everything the fingerprint deliberately excludes
    — i.e. the line numbers — is actually rewritten. A record whose metadata,
    document and embedding disagree is worse than a re-embed.
    """

    @staticmethod
    def _refresh_kwargs(tmp_path, src, edited):
        path = _write(tmp_path, src)
        idx, embedder, collection = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        before = embedder.calls
        collection.update_calls.clear()

        _write(tmp_path, edited)
        _index(idx, path, tmp_path)

        assert embedder.calls == before, "this fixture must take the skip path"
        assert collection.update_calls, "the skip path must still refresh records"
        return collection.update_calls[-1]

    def test_edge_call_lines_are_refreshed(self, tmp_path):
        """Impact analysis reports the call site, so a stale call_line misdirects it."""
        kwargs = self._refresh_kwargs(tmp_path, ORIGINAL, "# shifted\n" + ORIGINAL)

        edges = [
            (i, m) for i, m in zip(kwargs["ids"], kwargs["metadatas"]) if isinstance(i, str) and i.startswith("edge::")
        ]
        assert edges, "the fixture calls os.getenv, so an edge record must be refreshed"
        assert all("call_line" in m for _, m in edges)
        assert any(m["call_line"] > 1 for _, m in edges), "call_line must reflect the shifted source"

    def test_node_documents_carry_the_new_line(self, tmp_path):
        """The line is inside the embedded text, so the document must move with it."""
        kwargs = self._refresh_kwargs(tmp_path, ORIGINAL, "# shifted\n" + ORIGINAL)

        node_docs = [
            d for i, d in zip(kwargs["ids"], kwargs["documents"]) if isinstance(i, str) and not i.startswith("edge::")
        ]
        assert node_docs, "node records must be refreshed"
        for doc, meta in zip(node_docs, kwargs["metadatas"]):
            assert f"line {meta['line']}" in doc, "document and metadata must agree on the line"


class TestTheSkipPathCannotStrandARecord:
    """Both cases found by re-review: the skip must not be weaker than a full index."""

    def test_edge_resolution_is_recomputed_when_the_target_appears_later(self, tmp_path):
        """`resolved`/`target_id` are not extractor output — they depend on other files.

        A call to a not-yet-indexed function is stored `resolved: False`. Once the
        target exists, the caller's own graph shape is unchanged, so it takes the
        skip path forever. Without re-resolving there, the edge stays unresolved
        permanently and find_callers under-reports.
        """
        caller = tmp_path / "caller.py"
        caller.write_text("def fetch():\n    return helper()\n", encoding="utf-8")
        idx, _, collection = _indexer(tmp_path)
        _index(idx, str(caller), tmp_path)

        edge_id = "caller.fetch::helper"
        edge_id = next(r for r in collection.records if r.startswith("edge::"))
        assert collection.metadata_of(edge_id)["resolved"] is False, "target is unknown on the first pass"

        # The target now exists, and the caller gets a comment-only edit.
        target = tmp_path / "target.py"
        target.write_text("def helper():\n    return 1\n", encoding="utf-8")
        _index(idx, str(target), tmp_path)
        caller.write_text("# shifted\ndef fetch():\n    return helper()\n", encoding="utf-8")
        _index(idx, str(caller), tmp_path)

        assert collection.metadata_of(edge_id)["resolved"] is True, "the skip path must re-resolve edges"
        assert collection.metadata_of(edge_id)["target_id"], "target_id must be filled in once known"

    def test_a_record_an_earlier_run_failed_to_write_is_re_indexed_not_patched(self, tmp_path):
        """ChromaDB's update() drops unknown ids silently.

        If a node's embedding failed on an earlier run the record was never
        created. Patching it would report success while the record stayed
        missing — permanently, because the content hash is cached either way.
        """
        path = _write(tmp_path, ORIGINAL)
        idx, embedder, collection = _indexer(tmp_path)
        missing = "sample.fetch"
        collection.refuse_upsert_ids = {missing}
        _index(idx, path, tmp_path)
        assert missing not in collection.records, "fixture must leave one record unwritten"

        collection.refuse_upsert_ids = set()
        _write(tmp_path, "# shifted\n" + ORIGINAL)
        result = _index(idx, path, tmp_path)

        assert missing in collection.records, "the missing record must be created, not silently skipped"
        assert result.failed == 0
        assert embedder.calls > 0


class TestGraphChangesStillRebuild:
    @pytest.mark.parametrize(
        "mutation",
        [
            ("def fetch(", "def fetch_all("),
            ("class Service:", "class ServiceRenamed:"),
            ("    def run(self) -> bool:", "    def execute(self) -> bool:"),
            ("    return value", "    return len(value)"),
        ],
        ids=["renamed-function", "renamed-class", "renamed-method", "new-call-edge"],
    )
    def test_a_change_to_the_persisted_graph_re_embeds(self, tmp_path, mutation):
        path = _write(tmp_path, ORIGINAL)
        idx, embedder, _ = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls

        _write(tmp_path, ORIGINAL.replace(*mutation))
        _index(idx, path, tmp_path)

        assert embedder.calls > after_first, f"{mutation[0]!r} changed the persisted graph and must re-embed"

    @pytest.mark.parametrize(
        "mutation",
        [
            ("def fetch(user_id: int) -> str:", "def fetch(user_id: int, force: bool) -> str:"),
            ("import os", "import os\nimport sys"),
            ("    def run(self) -> bool:", "    def run(self, mode: str) -> bool:"),
        ],
        ids=["added-param", "added-import", "method-signature"],
    )
    def test_a_change_the_graph_does_not_record_is_correctly_skipped(self, tmp_path, mutation):
        """These look like interface changes, and are deliberately NOT re-embedded.

        The first implementation re-embedded them, because it hashed the AST
        interface. The extractor records none of it: a node is only
        ``(id, kind, name, parent, source_path, line)`` and its embedded text is
        ``"{KIND} {name}\nFile: {path} line {n}"``. Parameters, annotations and
        imports appear nowhere in any persisted record, so re-embedding on them
        buys an identical vector at full price.

        If the extractor ever starts recording signatures, this test fails —
        which is the correct alarm, since the fingerprint would then be blind to
        something real. Bump ``GRAPH_SHAPE_FINGERPRINT_VERSION`` at that point.
        """
        path = _write(tmp_path, ORIGINAL)
        idx, embedder, _ = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls

        _write(tmp_path, ORIGINAL.replace(*mutation))
        _index(idx, path, tmp_path)

        assert embedder.calls == after_first, f"{mutation[0]!r} changes nothing the graph stores"


class TestTheGraphIsNeverStale:
    """The two cases an AST-interface fingerprint got wrong (review of #13980).

    Both left the fingerprint equal while the extracted graph differed, so the
    skip path ran and the new records were never inserted — permanently, because
    the content hash was updated at the same time.
    """

    def test_renaming_a_nested_function_re_embeds(self, tmp_path):
        src = "def outer(x):\n    def inner(a):\n        return a\n    return inner\n"
        path = _write(tmp_path, src)
        idx, embedder, _ = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls

        _write(tmp_path, src.replace("inner", "inner_renamed"))
        _index(idx, path, tmp_path)

        assert embedder.calls > after_first, "a renamed closure is a new graph node and must be embedded"

    def test_changing_a_call_target_re_embeds(self, tmp_path):
        src = "import os\n\n\ndef fetch():\n    return os.getenv('X')\n"
        path = _write(tmp_path, src)
        idx, embedder, _ = _indexer(tmp_path)
        _index(idx, path, tmp_path)
        after_first = embedder.calls

        _write(tmp_path, src.replace("os.getenv('X')", "os.environ.get('X')"))
        _index(idx, path, tmp_path)

        assert embedder.calls > after_first, "a rewritten call target changes the persisted edge set"


class TestFailsOpen:
    def test_an_unfingerprintable_extraction_always_re_embeds(self, tmp_path):
        """A missing fingerprint must mean full re-analysis, never "unchanged"."""
        idx, embedder, _ = _indexer(tmp_path)
        path = _write(tmp_path, ORIGINAL)
        _index(idx, path, tmp_path)
        after_first = embedder.calls

        # Fingerprinting yields None (the fail-open path) on the next run.
        idx._shape_of = staticmethod(lambda extracted: None)
        _write(tmp_path, ORIGINAL.replace("    return value", "    return value  # touched"))
        _index(idx, path, tmp_path)

        assert embedder.calls > after_first, "no fingerprint must mean full re-analysis"

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

    def test_a_failed_line_refresh_clears_the_stored_fingerprint(self, tmp_path):
        """A refresh that fails must not leave the cache claiming the file is current."""
        path = _write(tmp_path, ORIGINAL)
        idx, _, collection = _indexer(tmp_path)
        _index(idx, path, tmp_path)

        collection.update_side_effect = RuntimeError("chroma down")
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
