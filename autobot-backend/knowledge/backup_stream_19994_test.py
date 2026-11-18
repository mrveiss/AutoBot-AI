# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19994: a backup with vectors is written in chunks, and restore reads the old form and the new."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from knowledge import backup_stream
from knowledge.bulk import BulkOperationsMixin

_VECTOR = {"embedding": [0.5, 0.25], "embedding_model": "m"}


class _KB(BulkOperationsMixin):
    def __init__(self, fail: bool = False) -> None:
        self.vector_store = object()
        self.fail = fail
        self.asked: list[int] = []

    async def _fetch_embeddings_from_vector_store(self, fact_ids):
        self.asked.append(len(fact_ids))
        if self.fail:
            raise RuntimeError("store down")
        return {fact_id: _VECTOR for fact_id in fact_ids}


def _doc(count: int, embeddings: bool = True) -> dict:
    return {
        "version": "1.0",
        "description": 'quote " and é',
        "include_embeddings": embeddings,
        "facts_count": count,
        "facts": [{"fact_id": f"f{i}", "content": f"c{i}"} for i in range(count)],
    }


@pytest.fixture
def small_batches(monkeypatch):
    monkeypatch.setattr(backup_stream, "EXPORT_BATCH_SIZE", 2)


@pytest.mark.parametrize(("compression", "name"), [(True, "b.jsongz"), (False, "b.json")])
async def test_it_reads_back_whole_with_each_vector(tmp_path: Path, small_batches, compression: bool, name: str):
    kb, path = _KB(), str(tmp_path / name)
    await backup_stream.write_backup(kb, path, _doc(5), compression)
    back = await kb._read_backup_file(path)
    assert back == {**_doc(5), "facts": [{**f, **_VECTOR} for f in _doc(5)["facts"]]}
    assert kb.asked == [2, 2, 1]


async def test_no_write_holds_more_than_one_batch_of_vectors(tmp_path: Path, small_batches, monkeypatch):
    writes: list[str] = []
    real = backup_stream._open_for_write

    def _recording(path, compression):
        out = real(path, compression)
        original = out.write
        out.write = lambda text: (writes.append(text), original(text))[1]
        return out

    monkeypatch.setattr(backup_stream, "_open_for_write", _recording)
    await backup_stream.write_backup(_KB(), str(tmp_path / "b.json"), _doc(5), False)
    counts = [w.count('"embedding":') for w in writes]
    assert sum(counts) == 5 and max(counts) <= 2


async def test_the_facts_given_do_not_keep_the_vectors(tmp_path: Path, small_batches):
    doc = _doc(3)
    await backup_stream.write_backup(_KB(), str(tmp_path / "b.json"), doc, False)
    assert all("embedding" not in fact for fact in doc["facts"])


async def test_the_file_is_durable_before_its_name_and_the_name_after(tmp_path: Path, monkeypatch):
    path, events = tmp_path / "b.jsongz", []
    real_replace = backup_stream.os.replace
    monkeypatch.setattr(backup_stream, "_fsync_path", lambda target: events.append(("fsync", target)))

    def _replace(src, dst):
        events.append(("replace", dst))
        real_replace(src, dst)

    monkeypatch.setattr(backup_stream.os, "replace", _replace)
    await backup_stream.write_backup(_KB(), str(path), _doc(1), True)
    assert events == [("fsync", f"{path}.partial"), ("replace", str(path)), ("fsync", str(tmp_path))]


async def test_a_gzip_backup_has_its_trailer_at_its_final_name(tmp_path: Path):
    path = tmp_path / "b.jsongz"
    await backup_stream.write_backup(_KB(), str(path), _doc(1), True)
    assert (await _KB()._read_backup_file(str(path)))["facts_count"] == 1  # a missing trailer raises EOFError


async def test_no_embeddings_asks_the_store_nothing(tmp_path: Path):
    kb, path = _KB(), str(tmp_path / "b.json")
    await backup_stream.write_backup(kb, path, _doc(2, embeddings=False), False)
    assert kb.asked == [] and (await kb._read_backup_file(path))["facts"] == _doc(2)["facts"]


async def test_no_facts_is_still_a_valid_document(tmp_path: Path):
    kb, path = _KB(), str(tmp_path / "b.json")
    await backup_stream.write_backup(kb, path, _doc(0), False)
    assert (await kb._read_backup_file(path))["facts"] == []


async def test_a_store_failure_keeps_the_facts_as_before(tmp_path: Path):
    kb, path = _KB(fail=True), str(tmp_path / "b.json")
    await backup_stream.write_backup(kb, path, _doc(2), False)
    assert (await kb._read_backup_file(path))["facts"] == _doc(2)["facts"]


async def test_a_failed_write_leaves_neither_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(backup_stream.json, "dumps", _raises)
    with pytest.raises(ValueError):
        await backup_stream.write_backup(_KB(), str(tmp_path / "b.json"), _doc(1), False)
    assert list(tmp_path.iterdir()) == []


def _raises(*_args, **_kwargs):
    raise ValueError("cannot encode")


def _write_old_form(path: Path, compression: bool) -> None:
    text = json.dumps({**_doc(1), "facts": [{"fact_id": "f0", **_VECTOR}]}, ensure_ascii=False, indent=2)
    if compression:
        with gzip.open(path, "wt", encoding="utf-8") as out:
            out.write(text)
    else:
        path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(("compression", "name"), [(True, "old.jsongz"), (False, "old.json")])
async def test_restore_reads_a_backup_in_the_old_form(tmp_path: Path, compression: bool, name: str):
    _write_old_form(tmp_path / name, compression)
    assert (await _KB()._read_backup_file(str(tmp_path / name)))["facts"][0]["embedding"] == [0.5, 0.25]
