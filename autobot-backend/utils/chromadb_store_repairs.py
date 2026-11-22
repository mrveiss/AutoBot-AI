# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Legacy in-place repairs for a local ChromaDB store (#1390, #2735, #18789).

``prepare_local_store`` is the single entry both local clients go through. Each
repair returns ``True`` when the store is in the repaired state (including "nothing
to do") and ``False`` when it failed; a failure is logged with its traceback and
never raises, so a broken repair cannot stop the client from opening. The path is
marked prepared only when all four succeed, so a failed repair is retried on the
next open instead of being skipped for the life of the process.

Concurrency: threads serialise on an in-process RLock; processes serialise on an
exclusive, bounded ``flock`` on ``.autobot_repair.lock`` in the store directory
(non-blocking attempts retried for ``REPAIR_LOCK_TIMEOUT_SECONDS``, then ``OSError``
so a stuck holder cannot hang a store open). ChromaDB
never lists the store root (it sizes and removes only its own per-segment
directories), so the dotfile is invisible to it.
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import json
import os
import pickle  # nosec B403  # restricted Unpickler below; see _RestrictedHnswUnpickler
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_LOCK_FILE_NAME = ".autobot_repair.lock"
REPAIR_LOCK_TIMEOUT_SECONDS = env_float_clamped(
    "AUTOBOT_CHROMA_REPAIR_LOCK_TIMEOUT_SECONDS", 30.0, 0.1, 3600.0, positive_finite=True
)
_LOCK_RETRY_INTERVAL_SECONDS = 0.05
_prepare_lock = threading.RLock()
_prepared_paths: set = set()


def _guarded(label: str) -> Callable:
    """Turn a repair into one that logs its failure with a traceback and returns False."""

    def decorate(fn: Callable[[Path], Any]) -> Callable[[Path], bool]:
        @functools.wraps(fn)
        def wrapper(chroma_path: Path) -> bool:
            try:
                return fn(chroma_path) is not False
            except Exception:
                logger.warning("%s failed", label, exc_info=True)
                return False

        return wrapper

    return decorate


@contextlib.contextmanager
def _open_db(chroma_path: Path, autocommit: bool = False) -> Iterator[Optional[sqlite3.Connection]]:
    """Yield a connection to chroma.sqlite3 (None when absent); always closed."""
    db_file = chroma_path / "chroma.sqlite3"
    if not db_file.exists():
        yield None
        return
    conn = sqlite3.connect(str(db_file), isolation_level=None if autocommit else "")
    try:
        yield conn
    finally:
        conn.close()


def _read_hnsw_params(cursor: sqlite3.Cursor, collection_id: str) -> dict:
    """Read HNSW metadata for one collection from collection_metadata table (#2735)."""
    cursor.execute(
        "SELECT key, str_value, int_value, float_value FROM collection_metadata WHERE collection_id=?",
        (collection_id,),
    )
    hnsw: dict = {}
    for key, sv, iv, fv in cursor.fetchall():
        if key.startswith("hnsw:"):
            hnsw[key[5:]] = sv if sv is not None else (iv if iv is not None else fv)
    return hnsw


def _build_collection_config_json(hnsw: dict) -> str:
    """Build the ChromaDB 0.5.x config_json_str from HNSW parameter dict (#2735)."""
    return json.dumps(
        {
            "hnsw_configuration": {
                "space": hnsw.get("space", "l2"),
                "ef_construction": hnsw.get("construction_ef", 100),
                "ef_search": hnsw.get("search_ef", 10),
                "num_threads": 4,
                "M": hnsw.get("M", 16),
                "resize_factor": 1.2,
                "batch_size": 100,
                "sync_threshold": 1000,
                "_type": "HNSWConfigurationInternal",
            },
            "_type": "CollectionConfigurationInternal",
        }
    )


@_guarded("ChromaDB config migration")
def _migrate_legacy_collection_configs(chroma_path: Path) -> bool:
    """Migrate ChromaDB collections missing _type in config_json_str.

    ChromaDB 0.5.x requires '_type' fields in collection config JSON.
    Collections created by older versions store config_json_str as '{}',
    which causes KeyError: '_type' on access. This patches the SQLite
    database directly before the PersistentClient opens it.
    """
    with _open_db(chroma_path) as conn:
        if conn is None:
            return True
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, config_json_str FROM collections")
        fixed = 0
        for cid, _name, config_str in cursor.fetchall():
            if "_type" in (json.loads(config_str) if config_str else {}):
                continue
            new_cfg = _build_collection_config_json(_read_hnsw_params(cursor, cid))
            cursor.execute("UPDATE collections SET config_json_str=? WHERE id=?", (new_cfg, cid))
            fixed += 1
        if fixed:
            conn.commit()
            logger.info("Migrated %d ChromaDB collection config(s) to 0.5.x format", fixed)
        return True


_SEGMENT_SPACE_SQL = (
    "SELECT s.id, cm.str_value FROM segments s "
    "JOIN collection_metadata cm ON cm.collection_id = s.collection "
    "WHERE s.scope = 'VECTOR' AND cm.key = 'hnsw:space' AND cm.str_value IS NOT NULL"
)


@_guarded("segment hnsw:space fix")
def _fix_segment_hnsw_space(chroma_path: Path) -> bool:
    """Copy hnsw:space from collection_metadata into segment_metadata.

    ChromaDB 0.5.23 stores hnsw:space in collection_metadata but reads
    it from segment_metadata when initializing the HNSW segment. If
    segment_metadata is empty the space defaults to L2, producing wrong
    distances even though the collection was created with cosine (#1390).
    """
    with _open_db(chroma_path) as conn:
        if conn is None:
            return True
        c = conn.cursor()
        c.execute(_SEGMENT_SPACE_SQL)
        fixed = 0
        for seg_id, space_val in c.fetchall():
            c.execute("SELECT 1 FROM segment_metadata WHERE segment_id = ? AND key = 'hnsw:space'", (seg_id,))
            if c.fetchone():
                continue
            c.execute(
                "INSERT INTO segment_metadata (segment_id, key, str_value) VALUES (?, 'hnsw:space', ?)",
                (seg_id, space_val),
            )
            fixed += 1
        if fixed:
            conn.commit()
            logger.info("Propagated hnsw:space to %d segment(s)", fixed)
        return True


_EMBEDDINGS_FIX_DDL = (
    "CREATE TABLE embeddings_fix ("
    "id INTEGER PRIMARY KEY, "
    "segment_id TEXT NOT NULL, "
    "embedding_id TEXT NOT NULL, "
    "seq_id INTEGER NOT NULL, "
    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, "
    "UNIQUE (segment_id, embedding_id))"
)
_SCHEMA_OBJECTS_SQL = (
    "SELECT sql FROM sqlite_master WHERE tbl_name = 'embeddings' "
    "AND type IN ('index', 'trigger') AND sql IS NOT NULL ORDER BY type, name"
)
_LEFTOVER_UNACCOUNTED_SQL = (
    "SELECT COUNT(*) FROM embeddings_fix f WHERE NOT EXISTS ("
    "SELECT 1 FROM embeddings e WHERE e.id = f.id "
    "AND e.segment_id = f.segment_id AND e.embedding_id = f.embedding_id)"
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone()
    return row is not None


def _column_types(conn: sqlite3.Connection, table: str) -> dict:
    """Column name -> declared type, in table order (``table`` is always a literal here)."""
    # Identifier, not a value: PRAGMA cannot bind a table name, and every caller passes a literal.
    pragma_sql = f"PRAGMA table_info({table})"  # nosec B608  # nosemgrep: autobot-sql-string-format
    return {row[1]: row[2] for row in conn.execute(pragma_sql)}


def _clear_leftover_copy(conn: sqlite3.Connection) -> bool:
    """Handle an ``embeddings_fix`` left behind by an earlier crashed run.

    Remove it only when the original ``embeddings`` table is intact AND every leftover
    row is accounted for in it (same id, segment_id, embedding_id): then the leftover
    is a pure duplicate. Anything else -- ``embeddings`` missing (the leftover may be
    the only copy of the data), or leftover rows ``embeddings`` does not hold -- is
    ambiguous: log it, change nothing, and report the repair as not done.
    """
    if not _table_exists(conn, "embeddings_fix"):
        return True
    if not _table_exists(conn, "embeddings"):
        logger.error("embeddings_fix exists but embeddings does not; leaving both alone for manual recovery")
        return False
    unaccounted = conn.execute(_LEFTOVER_UNACCOUNTED_SQL).fetchone()[0]
    if unaccounted:
        logger.error("embeddings_fix holds %d row(s) absent from embeddings; leaving it alone", unaccounted)
        return False
    conn.execute("DROP TABLE embeddings_fix")
    logger.info("Removed leftover embeddings_fix (duplicate of embeddings)")
    return True


def _copy_rows(conn: sqlite3.Connection) -> bool:
    """Copy embeddings into embeddings_fix by explicit column names; refuse on unknown columns."""
    old_cols, new_cols = list(_column_types(conn, "embeddings")), list(_column_types(conn, "embeddings_fix"))
    extra = [c for c in old_cols if c not in new_cols]
    if extra:
        logger.error("embeddings has columns %s that the rebuilt table lacks; refusing to drop them", extra)
        return False
    names = ", ".join(f'"{c}"' for c in new_cols if c in old_cols)
    # Identifiers, not values: column names read from the table's own schema, each double-quoted.
    insert_sql = f"INSERT INTO embeddings_fix ({names})"  # nosec B608  # nosemgrep: autobot-sql-string-format
    copy_sql = f"{insert_sql} SELECT {names} FROM embeddings"  # nosec B608  # nosemgrep: autobot-sql-string-format
    conn.execute(copy_sql)
    return True


def _swap_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE embeddings")
    conn.execute("ALTER TABLE embeddings_fix RENAME TO embeddings")


def _rebuild_embeddings(conn: sqlite3.Connection) -> bool:
    """create -> copy -> swap, then recreate the original indexes and triggers."""
    objects = [row[0] for row in conn.execute(_SCHEMA_OBJECTS_SQL)]
    conn.execute(_EMBEDDINGS_FIX_DDL)
    if not _copy_rows(conn):
        return False
    _swap_tables(conn)
    for sql in objects:
        conn.execute(sql)
    return True


def _rebuild_in_transaction(conn: sqlite3.Connection) -> bool:
    """Run the whole rebuild inside one ``BEGIN IMMEDIATE`` ... ``COMMIT``; ROLLBACK on any failure.

    ``conn`` must be in autocommit mode (``isolation_level=None``) so sqlite3 does not
    manage transactions around the DDL itself. Foreign keys are off and the legacy
    ALTER TABLE rename is on for the duration (SQLite's documented table-rebuild
    recipe); both PRAGMAs are no-ops inside a transaction, so they are set first.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA legacy_alter_table = ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            done = _clear_leftover_copy(conn) and _rebuild_embeddings(conn)
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT" if done else "ROLLBACK")
        return done
    finally:
        conn.execute("PRAGMA legacy_alter_table = OFF")


@_guarded("embeddings.seq_id fix")
def _fix_seq_id_blob_type(chroma_path: Path) -> bool:
    """Fix embeddings.seq_id BLOB->INTEGER for ChromaDB 0.5.x (#1390).

    ChromaDB 0.5.23 creates seq_id as BLOB but its Rust compactor
    expects INTEGER. Rebuild the table (atomically, keeping its indexes
    and triggers) before the compactor starts.
    """
    with _open_db(chroma_path, autocommit=True) as conn:
        if conn is None:
            return True
        if _column_types(conn, "embeddings").get("seq_id", "").upper() != "BLOB":
            return not (_table_exists(conn, "embeddings_fix") and not _table_exists(conn, "embeddings"))
        if not _rebuild_in_transaction(conn):
            return False
        logger.info("Fixed embeddings.seq_id BLOB->INTEGER")
        return True


def _infer_hnsw_dimensionality(segment_dir: Path) -> int:
    """Infer HNSW embedding dimensionality from binary files (#1390).

    Reads data_level0.bin size and element count to compute the
    vector dimension via hnswlib's internal record layout.
    Returns 0 if inference fails.
    """
    import struct

    data_file = segment_dir / "data_level0.bin"
    header_file = segment_dir / "header.bin"
    if not data_file.exists() or not header_file.exists():
        return 0
    try:
        file_size = data_file.stat().st_size
        with open(header_file, "rb") as f:
            hdr = f.read(52)
        vals = struct.unpack("<" + "I" * 13, hdr[:52])
        count = vals[5]
        if count == 0:
            return 0
        rec_size = file_size // count
        links_size = vals[11]
        label_size = 8
        dim = (rec_size - links_size - label_size) // 4
        if 64 <= dim <= 4096:
            return dim
    except Exception:
        pass
    return 0


# Issue #14187: index_metadata.pickle is ChromaDB's own on-disk format for
# PersistentLocalHnswSegment (chromadb/segment/impl/vector/local_persistent_hnsw.py)
# -- the library writes it with plain pickle.dump() and reads it back with plain
# pickle.load() itself, downstream of this function, so the file cannot move to a
# non-pickle format without forking the dependency. What this module controls is
# only its OWN read, performed solely to patch legacy metadata shapes before
# ChromaDB's loader runs (#1390).
#
# Trust boundary: the file lives under the local ChromaDB persist directory,
# which resolves under the SSOT/legacy data roots excluded from the filesystem
# MCP bridge (api/filesystem_mcp.py _EXCLUDED_DIR_PATHS, #14081/#14124). The only
# writers are ChromaDB's own segment code and this function, both running inside
# the backend process -- there is no known external write path today. Because
# "no known path today" is not proof for tomorrow (#14124's own history), the
# read here is restricted rather than trusted outright: find_class allows
# exactly ChromaDB's PersistentData class and nothing else, so a file written
# by anything other than ChromaDB's own persistence code fails closed instead
# of executing arbitrary code during deserialization.
_ALLOWED_HNSW_PICKLE_CLASSES = frozenset(
    {
        ("chromadb.segment.impl.vector.local_persistent_hnsw", "PersistentData"),
    }
)


class _RestrictedHnswUnpickler(pickle.Unpickler):
    """Unpickler for ``index_metadata.pickle`` restricted to ChromaDB's own class.

    Subclassing ``pickle.Unpickler`` (rather than calling ``pickle.load``/
    ``pickle.loads`` directly) keeps every GLOBAL/REDUCE opcode gated by
    ``find_class``: only ``PersistentData`` may be constructed, and builtin
    containers (dict/list/str/int/None) used by its fields never go through
    ``find_class`` at all, so legitimate files are unaffected.
    """

    def find_class(self, module: str, name: str) -> Any:
        if (module, name) not in _ALLOWED_HNSW_PICKLE_CLASSES:
            raise pickle.UnpicklingError(
                f"Refusing to unpickle disallowed class {module}.{name} from index_metadata.pickle"
            )
        return super().find_class(module, name)


def _atomic_pickle_dump(obj: Any, target: Path) -> None:
    """Write ``obj`` to ``target`` so a reader sees the old file or the new one, never a torso.

    Temp file in the same directory (same filesystem, so ``os.replace`` is atomic),
    flushed and fsynced before the rename; the temp file is removed on any failure.
    """
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".index_metadata.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(obj, f)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, target.stat().st_mode & 0o7777)
        os.replace(tmp_name, target)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise
    _fsync_dir(target.parent)


def _fsync_dir(directory: Path) -> None:
    """Make the rename durable; best-effort, since not every platform can fsync a directory."""
    try:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        logger.warning("Could not fsync directory %s after pickle rewrite", directory, exc_info=True)


def _sweep_stale_pickle_temps(chroma_path: Path) -> None:
    """Remove ``.index_metadata.*.tmp`` left behind by a killed rewrite.

    These are this module's own temp files (the exact ``mkstemp`` prefix and suffix
    used by ``_atomic_pickle_dump``), never user data; the real pickle is untouched.
    """
    for tmp in chroma_path.glob("*/.index_metadata.*.tmp"):
        try:
            tmp.unlink()
            logger.info("Removed stale pickle temp file %s", tmp)
        except FileNotFoundError:
            continue


def _repaired_pickle_object(data: Any, pkl_dir: Path, persistent_data_cls: type) -> Any:
    """Return the object to write back, or None when the pickle needs no fix."""
    is_dict = isinstance(data, dict)
    dim = data.get("dimensionality") if is_dict else getattr(data, "dimensionality", None)
    if not is_dict and dim is not None:
        return None
    if dim is None:
        dim = _infer_hnsw_dimensionality(pkl_dir) or None
    if not is_dict:
        data.dimensionality = dim
        return data
    return persistent_data_cls(
        dimensionality=dim,
        total_elements_added=data.get("total_elements_added", 0),
        id_to_label=data.get("id_to_label", {}),
        label_to_id=data.get("label_to_id", {}),
        id_to_seq_id=data.get("id_to_seq_id", {}),
    )


def _fix_one_hnsw_pickle(pkl_file: Path, persistent_data_cls: type) -> None:
    with open(pkl_file, "rb") as f:
        data = _RestrictedHnswUnpickler(f).load()
    obj = _repaired_pickle_object(data, pkl_file.parent, persistent_data_cls)
    if obj is None:
        return
    _atomic_pickle_dump(obj, pkl_file)
    logger.info("Fixed HNSW pickle: %s (dim=%s)", pkl_file.parent.name[:8], obj.dimensionality)


@_guarded("HNSW pickle fix")
def _fix_hnsw_pickle_format(chroma_path: Path) -> bool:
    """Fix HNSW index_metadata.pickle for ChromaDB 0.5.x (#1390).

    ChromaDB 0.5.23 may serialize HNSW metadata as a plain dict
    (reader expects PersistentData) and/or leave dimensionality
    as None (HNSW init requires an int). This patches both. Every file is
    attempted; returns False if any failed.
    """
    try:
        # Issue #3016: lazy import — chromadb is heavy
        from chromadb.segment.impl.vector.local_persistent_hnsw import PersistentData
    except ImportError:
        return True

    _sweep_stale_pickle_temps(chroma_path)
    ok = True
    for pkl_file in chroma_path.glob("*/index_metadata.pickle"):
        try:
            _fix_one_hnsw_pickle(pkl_file, PersistentData)
        except Exception as e:
            ok = False
            logger.warning("HNSW pickle fix failed for %s: %s", pkl_file, e, exc_info=True)
    return ok


def _flock_with_timeout(fd: int) -> None:
    """Take LOCK_EX without blocking, retrying until the deadline; raise OSError on timeout."""
    deadline = time.monotonic() + REPAIR_LOCK_TIMEOUT_SECONDS
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise OSError(f"repair lock not acquired within {REPAIR_LOCK_TIMEOUT_SECONDS}s") from None
            time.sleep(_LOCK_RETRY_INTERVAL_SECONDS)


@contextlib.contextmanager
def _cross_process_lock(chroma_path: Path) -> Iterator[None]:
    """Hold an exclusive flock on the store's lock file; a second process waits here, bounded."""
    fd = os.open(chroma_path / _LOCK_FILE_NAME, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        _flock_with_timeout(fd)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _run_repairs(chroma_path: Path) -> bool:
    """Run all four repairs (none is skipped because another failed); True only if all succeeded."""
    results = [
        _migrate_legacy_collection_configs(chroma_path),
        _fix_segment_hnsw_space(chroma_path),
        _fix_seq_id_blob_type(chroma_path),
        _fix_hnsw_pickle_format(chroma_path),
    ]
    return all(r is not False for r in results)


def _locked(chroma_path: Path, run: Callable[[Path], bool]) -> Optional[bool]:
    """Run ``run`` under the cross-process lock; None when the lock was not obtained.

    Only the acquisition is inside the ``except OSError``: an OSError raised by a
    repair is the repair's own failure and is handled by its guard, not mislogged as
    a lock failure.
    """
    lock = _cross_process_lock(chroma_path)
    try:
        lock.__enter__()
    except OSError:
        logger.warning("ChromaDB repair lock unavailable for %s", chroma_path, exc_info=True)
        return None
    try:
        return run(chroma_path)
    finally:
        lock.__exit__(None, None, None)


def prepare_local_store(chroma_path: Path) -> None:
    """Create the path and run the 4 legacy repairs; mark it prepared only if all succeeded.

    Never raises for a failed repair or an unobtainable lock: the client still opens,
    and the next call retries because the path was not marked. Already-prepared paths
    return without taking any lock. Threads serialise on ``_prepare_lock`` because a
    second thread would only repeat the same repairs; the wait is bounded by the
    cross-process lock timeout, after which the next thread retries.
    """
    key = str(chroma_path.resolve())
    if key in _prepared_paths:
        return
    with _prepare_lock:
        if key in _prepared_paths:
            return
        chroma_path.mkdir(parents=True, exist_ok=True)
        ok = _locked(chroma_path, _run_repairs)
        if ok is None:
            return
        if ok:
            _prepared_paths.add(key)
        else:
            logger.warning("ChromaDB store %s not marked prepared; repairs retry on next open", chroma_path)


def repair_hnsw_pickles_locked(chroma_path: Path) -> bool:
    """Re-run only the pickle repair under the same locks (for after a re-index writes new pickles).

    ``prepare_local_store`` is a no-op once a path is marked prepared, so it cannot
    serve this: indexing rewrites ``index_metadata.pickle`` after the store opened.
    Returns False, and logs, when the lock was unobtainable or the repair failed.
    """
    with _prepare_lock:
        ok = _locked(chroma_path, _fix_hnsw_pickle_format)
    if not ok:
        logger.warning("HNSW pickle repair did not complete for %s", chroma_path)
    return bool(ok)
