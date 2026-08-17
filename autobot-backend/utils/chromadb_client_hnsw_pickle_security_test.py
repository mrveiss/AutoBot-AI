# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14187: index_metadata.pickle deserialization must not run arbitrary code.

``utils.chromadb_client._fix_hnsw_pickle_format`` reads ChromaDB's own
``index_metadata.pickle`` (chromadb's ``PersistentLocalHnswSegment``
format) to patch legacy metadata shapes before ChromaDB's own loader runs
(#1390). It used a plain ``pickle.load()`` -- any writable path to that
file became arbitrary code execution the moment this function ran.
``_RestrictedHnswUnpickler`` gates every class reference through
``find_class`` and allows exactly ChromaDB's ``PersistentData``, nothing
else.

These tests build the real ``chromadb.segment.impl.vector.local_persistent_hnsw``
leaf module by hand (never importing the real ``chromadb`` package): CI's
``conftest.py`` globally stubs ``chromadb`` with an empty ``__path__`` (see
its "Stub chromadb before it is imported" block) because the real package
hangs at import time without a local server, and the actual dependency also
needs ``hnswlib`` which is not guaranteed present in every job that runs
this file. Registering the leaf module directly under its full dotted name
in ``sys.modules`` is sufficient: Python's import machinery resolves a
fully-qualified name straight from ``sys.modules`` without walking parent
packages, which is also exactly how ``pickle``'s own ``find_class`` resolves
a GLOBAL opcode. Verified against CPython's import machinery, not assumed.
"""

from __future__ import annotations

import importlib.util
import io
import logging
import os
import pickle
import sys
import types
from pathlib import Path

import pytest

_MODULE_NAME = "chromadb.segment.impl.vector.local_persistent_hnsw"
_CLASS_NAME = "PersistentData"


def _load_real_chromadb_client_module():
    """Return the real ``utils.chromadb_client`` module.

    #13162 established that some test modules install a permanent MagicMock
    placeholder for ``utils.chromadb_client`` / ``utils.async_chromadb_client``
    in ``sys.modules`` and never remove it, so whichever test collects first
    wins the shared module. Load the real file under a private name when
    that has happened, mirroring
    ``chromadb_client_cache_key_test.py::_load_real_chromadb_modules``.
    """
    cached = sys.modules.get("utils.chromadb_client")
    if cached is not None and getattr(cached, "__file__", None):
        return cached
    private = "_real_14187_chromadb_client"
    cached_private = sys.modules.get(private)
    if cached_private is not None:
        return cached_private
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(private, here / "chromadb_client.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[private] = module
    spec.loader.exec_module(module)
    return module


def _ensure_stub_module_chain(dotted: str) -> None:
    """Register every missing package level of ``dotted`` as a minimal stub.

    Real or already-stubbed modules (e.g. ``chromadb`` itself, which
    ``conftest.py`` stubs globally) are left untouched -- only genuinely
    missing intermediate levels get a placeholder. Needed because
    ``pickle``'s own ``save_global`` re-validates the full parent chain via
    ``getattr``, which is stricter than a plain ``import`` statement (proven
    against CPython's pickle module, not assumed).
    """
    parts = dotted.split(".")
    prefix_parts: list[str] = []
    for index, part in enumerate(parts):
        prefix_parts.append(part)
        prefix = ".".join(prefix_parts)
        if prefix in sys.modules:
            continue
        stub = types.ModuleType(prefix)
        if index < len(parts) - 1:
            stub.__path__ = []  # marks it as a package for the import system
        sys.modules[prefix] = stub
        parent = prefix.rpartition(".")[0]
        if parent:
            setattr(sys.modules[parent], part, stub)


def _install_real_persistent_data_class() -> type:
    """Register a ``PersistentData`` stand-in at ChromaDB's real module path.

    Registered under the leaf module's fully-qualified name so resolution
    works regardless of whether the real ``chromadb`` package (or
    ``conftest.py``'s stub of it) is present. The class shape matches
    ``chromadb.segment.impl.vector.local_persistent_hnsw.PersistentData``
    (see that file): five plain fields, no exotic types.
    """
    existing = sys.modules.get(_MODULE_NAME)
    if existing is not None and isinstance(getattr(existing, _CLASS_NAME, None), type):
        return getattr(existing, _CLASS_NAME)

    class PersistentData:
        def __init__(self, dimensionality, total_elements_added, id_to_label, label_to_id, id_to_seq_id):
            self.dimensionality = dimensionality
            self.total_elements_added = total_elements_added
            self.id_to_label = id_to_label
            self.label_to_id = label_to_id
            self.id_to_seq_id = id_to_seq_id

    PersistentData.__module__ = _MODULE_NAME
    PersistentData.__qualname__ = _CLASS_NAME

    _ensure_stub_module_chain(_MODULE_NAME)
    sys.modules[_MODULE_NAME].PersistentData = PersistentData
    return PersistentData


sync_mod = _load_real_chromadb_client_module()
PersistentData = _install_real_persistent_data_class()


def _persistent_data_bytes() -> bytes:
    obj = PersistentData(
        dimensionality=8,
        total_elements_added=2,
        id_to_label={"doc-a": 0, "doc-b": 1},
        label_to_id={0: "doc-a", 1: "doc-b"},
        id_to_seq_id={"doc-a": 1, "doc-b": 2},
    )
    return pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)


def _disallowed_class_bytes() -> bytes:
    """A pickle stream whose GLOBAL opcode names a disallowed class.

    Built from a real, harmless function reference (``os.system``) rather
    than a committed opaque blob. Pickling a bare function reference never
    calls it -- there is nothing here that executes on load even without
    the allowlist; the test exists to prove the allowlist rejects the class
    reference itself, which is the same resolution step a ``__reduce__``
    based RCE gadget depends on.
    """
    return pickle.dumps(os.system, protocol=pickle.HIGHEST_PROTOCOL)


# ---------------------------------------------------------------------------
# _RestrictedHnswUnpickler
# ---------------------------------------------------------------------------


def test_restricted_unpickler_accepts_the_allowlisted_class():
    """A legitimate PersistentData payload still round-trips."""
    loaded = sync_mod._RestrictedHnswUnpickler(io.BytesIO(_persistent_data_bytes())).load()
    assert isinstance(loaded, PersistentData)
    assert loaded.dimensionality == 8
    assert loaded.id_to_label == {"doc-a": 0, "doc-b": 1}
    assert loaded.id_to_seq_id == {"doc-a": 1, "doc-b": 2}


def test_restricted_unpickler_rejects_disallowed_class():
    """A class reference outside the allowlist is refused, not executed."""
    with pytest.raises(pickle.UnpicklingError):
        sync_mod._RestrictedHnswUnpickler(io.BytesIO(_disallowed_class_bytes())).load()


# ---------------------------------------------------------------------------
# _fix_hnsw_pickle_format (integration)
# ---------------------------------------------------------------------------


def _collection_dir(tmp_path: Path) -> Path:
    collection_dir = tmp_path / "11111111-1111-1111-1111-111111111111"
    collection_dir.mkdir()
    return collection_dir


def test_fix_hnsw_pickle_format_migrates_legacy_dict_without_data_loss(tmp_path):
    """The pre-0.5.x plain-dict shape is still readable and still migrated.

    Plain dict/int/str payloads never invoke ``find_class`` at all (only
    GLOBAL/REDUCE opcodes for custom classes do), so the restricted
    unpickler does not need an allowlist entry for them -- this is the
    "no data loss" proof for every ``index_metadata.pickle`` written before
    ChromaDB 0.5.x's PersistentData-only format.
    """
    collection_dir = _collection_dir(tmp_path)
    pkl_file = collection_dir / "index_metadata.pickle"
    legacy_shape = {
        "dimensionality": 8,
        "total_elements_added": 2,
        "id_to_label": {"doc-a": 0},
        "label_to_id": {0: "doc-a"},
        "id_to_seq_id": {"doc-a": 1},
    }
    with open(pkl_file, "wb") as f:
        pickle.dump(legacy_shape, f)

    sync_mod._fix_hnsw_pickle_format(tmp_path)

    with open(pkl_file, "rb") as f:
        migrated = sync_mod._RestrictedHnswUnpickler(f).load()
    assert isinstance(migrated, PersistentData)
    assert migrated.dimensionality == 8
    assert migrated.id_to_label == {"doc-a": 0}


def test_fix_hnsw_pickle_format_skips_disallowed_pickle_without_raising(tmp_path, caplog):
    """A file that isn't ChromaDB's own format is refused, not executed.

    Proves the security property at the call site this issue is about, not
    just at the unpickler unit level: the malicious/foreign bytes are never
    turned into a live object, the function does not raise out of the
    caller's loop, and the on-disk bytes are left untouched (not silently
    "fixed" into something derived from an unpicklable payload).
    """
    collection_dir = _collection_dir(tmp_path)
    pkl_file = collection_dir / "index_metadata.pickle"
    original_bytes = _disallowed_class_bytes()
    with open(pkl_file, "wb") as f:
        f.write(original_bytes)

    with caplog.at_level(logging.WARNING):
        sync_mod._fix_hnsw_pickle_format(tmp_path)  # must not raise

    untouched = pkl_file.read_bytes() == original_bytes
    assert untouched, "disallowed pickle must be left untouched, not rewritten"
    # Assert the SPECIFIC refusal message, not just "some warning fired": an
    # unrestricted pickle.load() would also raise on this payload (a builtin
    # function has no settable __dict__), landing in the same outer except and
    # logging *some* warning -- but never this message, which only find_class
    # produces. This is what makes the assertion mutation-sensitive: bypassing
    # the allowlist changes the logged text, not just whether something logged.
    refused = any("Refusing to unpickle disallowed class" in rec.message for rec in caplog.records)
    assert refused, "the allowlist must be what rejects this payload, not an incidental failure"
