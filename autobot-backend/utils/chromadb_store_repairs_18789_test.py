# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18789 review findings: repair success gating, atomic rebuild, atomic pickle, repair lock."""

import fcntl
import logging
import sqlite3
import time
from unittest.mock import MagicMock, patch

import pytest

from utils import chromadb_store_repairs as repairs

_REPAIRS = (
    "_migrate_legacy_collection_configs",
    "_fix_segment_hnsw_space",
    "_fix_seq_id_blob_type",
    "_fix_hnsw_pickle_format",
)


@pytest.fixture(autouse=True)
def _fresh_prepared():
    repairs._prepared_paths.clear()
    yield
    repairs._prepared_paths.clear()


def test_failed_repair_is_not_marked_prepared_and_retries(tmp_path):
    store = tmp_path / "store"
    mocks = {n: MagicMock(return_value=True) for n in _REPAIRS}
    mocks["_fix_seq_id_blob_type"].return_value = False
    with patch.multiple(repairs, **mocks):
        repairs.prepare_local_store(store)
        assert not repairs._prepared_paths
        repairs.prepare_local_store(store)
        assert mocks["_fix_seq_id_blob_type"].call_count == 2
        mocks["_fix_seq_id_blob_type"].return_value = True
        repairs.prepare_local_store(store)
        assert len(repairs._prepared_paths) == 1
        repairs.prepare_local_store(store)
        assert mocks["_fix_seq_id_blob_type"].call_count == 3


def test_a_raising_repair_reports_false_with_traceback_and_does_not_raise(tmp_path, caplog):
    (tmp_path / "chroma.sqlite3").write_bytes(b"not a database")
    assert repairs._migrate_legacy_collection_configs(tmp_path) is False
    assert any(r.exc_info for r in caplog.records)


_LEGACY_DDL = (
    "CREATE TABLE embeddings (id INTEGER PRIMARY KEY, segment_id TEXT NOT NULL, "
    "embedding_id TEXT NOT NULL, seq_id BLOB NOT NULL, "
    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE (segment_id, embedding_id))",
    "CREATE INDEX idx_emb_seg ON embeddings (segment_id)",
    "CREATE TABLE audit (n INTEGER)",
    "CREATE TRIGGER trg_emb AFTER INSERT ON embeddings BEGIN INSERT INTO audit VALUES (new.id); END",
)
_ROWS = [(1, "s1", "a", 5, "2026-01-01 00:00:00"), (2, "s1", "b", 6, "2026-01-02 00:00:00")]


def _make_db(path):
    conn = sqlite3.connect(str(path / "chroma.sqlite3"))
    for ddl in _LEGACY_DDL:
        conn.execute(ddl)
    conn.executemany(
        "INSERT INTO embeddings (id, segment_id, embedding_id, seq_id, created_at) VALUES (?,?,?,?,?)",
        [(i, s, e, q.to_bytes(8, "big"), c) for i, s, e, q, c in _ROWS],
    )
    conn.commit()
    conn.close()


def _snapshot(path):
    conn = sqlite3.connect(str(path / "chroma.sqlite3"))
    try:
        rows = conn.execute("SELECT id, segment_id, embedding_id, created_at FROM embeddings ORDER BY id").fetchall()
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
        seq_type = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(embeddings)")}["seq_id"]
        return rows, names, seq_type
    finally:
        conn.close()


def test_rebuild_keeps_rows_index_and_trigger_and_leaves_no_fix_table(tmp_path):
    _make_db(tmp_path)
    before_rows = _snapshot(tmp_path)[0]
    assert repairs._fix_seq_id_blob_type(tmp_path) is True
    rows, names, seq_type = _snapshot(tmp_path)
    assert rows == before_rows
    assert seq_type.upper() == "INTEGER"
    assert {"idx_emb_seg", "trg_emb"} <= names
    assert "embeddings_fix" not in names
    conn = sqlite3.connect(str(tmp_path / "chroma.sqlite3"))
    conn.execute("INSERT INTO embeddings (segment_id, embedding_id, seq_id) VALUES ('s2','c',9)")
    assert conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == len(_ROWS) + 1  # trigger still fires
    conn.close()


def test_rebuild_failing_midway_rolls_back_to_the_original(tmp_path):
    _make_db(tmp_path)
    before = _snapshot(tmp_path)
    with patch.object(repairs, "_swap_tables", side_effect=RuntimeError("boom after insert")):
        assert repairs._fix_seq_id_blob_type(tmp_path) is False
    after = _snapshot(tmp_path)
    assert after == before
    assert "embeddings_fix" not in after[1]
    assert after[2].upper() == "BLOB"


def test_leftover_duplicate_copy_is_cleared_and_rebuild_proceeds(tmp_path):
    _make_db(tmp_path)
    conn = sqlite3.connect(str(tmp_path / "chroma.sqlite3"))
    conn.execute("CREATE TABLE embeddings_fix AS SELECT * FROM embeddings")
    conn.commit()
    conn.close()
    assert repairs._fix_seq_id_blob_type(tmp_path) is True
    rows, names, seq_type = _snapshot(tmp_path)
    assert len(rows) == 2 and "embeddings_fix" not in names and seq_type.upper() == "INTEGER"


def test_leftover_with_unaccounted_rows_is_left_alone(tmp_path):
    _make_db(tmp_path)
    conn = sqlite3.connect(str(tmp_path / "chroma.sqlite3"))
    conn.execute("CREATE TABLE embeddings_fix AS SELECT * FROM embeddings")
    conn.execute("INSERT INTO embeddings_fix VALUES (99, 'sX', 'only-here', 1, '2026-01-03 00:00:00')")
    conn.commit()
    conn.close()
    assert repairs._fix_seq_id_blob_type(tmp_path) is False
    rows, names, seq_type = _snapshot(tmp_path)
    assert "embeddings_fix" in names and seq_type.upper() == "BLOB" and len(rows) == 2
    conn = sqlite3.connect(str(tmp_path / "chroma.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM embeddings_fix").fetchone()[0] == 3
    conn.close()


def test_atomic_pickle_write_failure_keeps_original_and_leaves_no_temp(tmp_path):
    target = tmp_path / "index_metadata.pickle"
    target.write_bytes(b"original-bytes")
    with patch.object(repairs.pickle, "dump", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            repairs._atomic_pickle_dump({"a": 1}, target)
    assert target.read_bytes() == b"original-bytes"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_pickle_write_replaces_and_preserves_mode(tmp_path):
    target = tmp_path / "index_metadata.pickle"
    target.write_bytes(b"old")
    target.chmod(0o644)
    repairs._atomic_pickle_dump({"a": 1}, target)
    assert repairs.pickle.loads(target.read_bytes()) == {"a": 1}  # nosec B301
    assert target.stat().st_mode & 0o777 == 0o644
    assert list(tmp_path.iterdir()) == [target]


def test_repairs_run_under_an_exclusive_flock_that_is_released(tmp_path):
    order = []
    with (
        patch.object(repairs.fcntl, "flock", side_effect=lambda fd, op: order.append(("flock", op))),
        patch.object(repairs, "_run_repairs", side_effect=lambda p: order.append(("repairs", None)) or True),
    ):
        repairs.prepare_local_store(tmp_path / "store")
    assert order == [("flock", fcntl.LOCK_EX | fcntl.LOCK_NB), ("repairs", None), ("flock", fcntl.LOCK_UN)]
    assert (tmp_path / "store" / repairs._LOCK_FILE_NAME).exists()


def _blocked(*_a):
    raise BlockingIOError


def test_a_stuck_lock_holder_times_out_without_hanging_or_marking(tmp_path, caplog):
    store = tmp_path / "store"
    with (
        patch.object(repairs.fcntl, "flock", side_effect=_blocked),
        patch.object(repairs, "REPAIR_LOCK_TIMEOUT_SECONDS", 0.2),
        patch.object(repairs, "_run_repairs") as run,
        caplog.at_level(logging.WARNING),
    ):
        started = time.monotonic()
        repairs.prepare_local_store(store)
        elapsed = time.monotonic() - started
    assert elapsed < 3
    run.assert_not_called()
    assert repairs._prepared_paths == set()
    assert "repair lock unavailable" in caplog.text


def test_lock_acquired_on_the_third_attempt_marks_the_path(tmp_path):
    calls = []

    def flaky(fd, op):
        calls.append(op)
        if len(calls) < 3 and op & fcntl.LOCK_NB:
            raise BlockingIOError

    with (
        patch.object(repairs.fcntl, "flock", side_effect=flaky),
        patch.object(repairs, "_LOCK_RETRY_INTERVAL_SECONDS", 0.001),
        patch.object(repairs, "_run_repairs", return_value=True),
    ):
        repairs.prepare_local_store(tmp_path / "store")
    assert len(calls) == 4  # 3 attempts + unlock
    assert str((tmp_path / "store").resolve()) in repairs._prepared_paths


def test_oserror_inside_a_repair_is_a_repair_failure_not_a_lock_failure(tmp_path, caplog):
    store = tmp_path / "store"
    with (
        patch.object(repairs.Path, "glob", side_effect=OSError("readdir boom")),
        patch.object(repairs, "_migrate_legacy_collection_configs", return_value=True),
        patch.object(repairs, "_fix_segment_hnsw_space", return_value=True),
        patch.object(repairs, "_fix_seq_id_blob_type", return_value=True),
        patch.dict("sys.modules", {"chromadb.segment.impl.vector.local_persistent_hnsw": MagicMock()}),
        caplog.at_level(logging.WARNING),
    ):
        repairs.prepare_local_store(store)
    assert "HNSW pickle fix failed" in caplog.text
    assert "repair lock unavailable" not in caplog.text
    assert repairs._prepared_paths == set()


def test_stale_temp_is_swept_and_the_real_pickle_is_untouched(tmp_path):
    seg = tmp_path / "seg"
    seg.mkdir()
    stale = seg / ".index_metadata.abc123.tmp"
    stale.write_bytes(b"partial")
    real = seg / "index_metadata.pickle"
    real.write_bytes(b"real")
    other = seg / "notes.tmp"
    other.write_bytes(b"user")
    repairs._sweep_stale_pickle_temps(tmp_path)
    assert not stale.exists()
    assert real.read_bytes() == b"real"
    assert other.exists()


def test_atomic_pickle_write_fsyncs_the_directory(tmp_path):
    target = tmp_path / "index_metadata.pickle"
    target.write_bytes(b"old")
    with patch.object(repairs, "_fsync_dir") as fsync_dir:
        repairs._atomic_pickle_dump({"a": 1}, target)
    fsync_dir.assert_called_once_with(tmp_path)


def test_fsync_dir_failure_is_logged_not_raised(tmp_path, caplog):
    with patch.object(repairs.os, "fsync", side_effect=OSError("nope")), caplog.at_level(logging.WARNING):
        repairs._fsync_dir(tmp_path)
    assert "Could not fsync directory" in caplog.text


def test_locked_pickle_entry_reports_false_when_lock_unobtainable(tmp_path):
    with (
        patch.object(repairs.fcntl, "flock", side_effect=_blocked),
        patch.object(repairs, "REPAIR_LOCK_TIMEOUT_SECONDS", 0.1),
    ):
        assert repairs.repair_hnsw_pickles_locked(tmp_path) is False


def test_locked_pickle_entry_runs_the_pickle_repair_under_the_lock(tmp_path):
    with patch.object(repairs, "_fix_hnsw_pickle_format", return_value=True) as fix:
        assert repairs.repair_hnsw_pickles_locked(tmp_path) is True
    fix.assert_called_once_with(tmp_path)
