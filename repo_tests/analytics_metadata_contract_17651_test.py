# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The keys analytics endpoints FILTER on must be keys the writers EMIT (#17651).

`_prepare_problem_document` added `source_id` only ``if source_id:``. Every
codebase-analytics endpoint filters ``{"source_id": source_id}``. Each side was
internally consistent and nobody compared them, so an indexing run that supplied
no source_id wrote **11,241 rows no per-source query could match** -- present,
healthy, unreachable -- and the panels rendered an honest zero.

Both sides are always correct in isolation; the defect lives only in the gap, so
no test of either side can see it. That is what this file is for.

EVERY DETECTOR HERE HAS A CONTRAST PAIR (#17672 review). A detector exercised
only against the live tree is exercised against the one input it is guaranteed
to agree with -- it can be narrowed later and nothing fails. The fixtures below
are synthetic source strings: one each detector must recognise, one it must
reject.
"""

from __future__ import annotations

from repo_tests._analytics_metadata_detect import (
    ENGINE_SUPPLIED,
    filter_keys,
    inline_write_site_keys,
    metadata_binders,
    preparers,
)
from repo_tests._paths import repo_root

_ANALYTICS = repo_root() / "autobot-backend" / "api" / "codebase_analytics"
_WRITER = _ANALYTICS / "chromadb_storage.py"


def _writer_source() -> str:
    return _WRITER.read_text(encoding="utf-8")


def _emitted_keys() -> set[str]:
    found = preparers(_writer_source())
    assert found, "no _prepare_*_document functions found — re-derive, do not pass vacuously"
    return set().union(*found.values()) | inline_write_site_keys(_writer_source())


#: The writer's collection. A module is a reader of THIS contract when it
#: obtains that collection -- not when it happens to filter on `source_id`.
_COLLECTION_ACCESSOR = "get_code_collection"


def _reader_filter_keys() -> dict[str, set[str]]:
    """Filter keys of every module that reads the writer's collection.

    #17672 review (e5): the first version globbed `endpoints/*.py`. The
    writer's collection is `autobot_code`, and modules outside that directory
    obtain it too -- `analytics_debt.py`, `analytics_quality.py` and
    `analytics_code.py` all filter on it. A guard asserting a writer-reader
    contract that examines only some readers is the defect it was written to
    catch, one directory along.

    The population is discovered by **obtaining the collection**, which is also
    what keeps it honest in the other direction: `bug_predictor.py` and
    `detector.py` both carry `source_id` where-filters and are NOT in scope,
    because they query `bug_pattern_vectors` and `cross_language_patterns`.
    One of them even comments that its filter "mirrors the dependencies.py
    source_id where-filter", which is exactly what makes it look in-scope.
    **A `source_id` filter is not evidence of this contract; the collection is.**
    """
    backend = repo_root() / "autobot-backend"
    found: dict[str, set[str]] = {}
    for path in sorted(backend.rglob("*.py")):
        if "test" in path.name or "/tests/" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if _COLLECTION_ACCESSOR not in text:
            continue
        keys = filter_keys(text)
        if keys:
            found[str(path.relative_to(backend))] = keys
    assert found, f"no module referencing {_COLLECTION_ACCESSOR} filters on anything — re-derive"
    return found


# ---------------------------------------------------------------- contrasts

_EMITS = """
def _prepare_thing_document(thing, source_id=None):
    metadata = {"type": "thing", "file_path": thing["p"]}
    if source_id:
        metadata["source_id"] = source_id
    return metadata
"""

_MENTIONS_WITHOUT_EMITTING = """
def _prepare_thing_document(thing, source_id=None):
    audit = {"source_id": source_id}          # a different dict
    log(audit["source_id"])
    metadata = {"type": "thing"}
    return metadata
"""

_INLINE_WRITE = """
async def _store(collection, source_id):
    await collection.upsert(ids=["a"], metadatas=[{"source_id": source_id, "type": "x"}])
"""

_FILTERS = """
def endpoint(source_id):
    where_filter = {"$and": [{"type": {"$in": ["function"]}}, {"source_id": source_id}]}
    return get_all(collection, where=where_filter)
"""

_NO_FILTER = """
def endpoint():
    payload = {"total": 0, "rows": []}
    return payload
"""


def test_the_emitted_key_detector_reads_the_metadata_binding_not_the_function() -> None:
    """Positive and negative for the #17672 `:62` narrowing.

    The rejected fixture mentions `source_id` in a *different* dict. The first
    version of this detector counted that and passed, which meant a preparer
    could stop emitting the key while the test stayed green.
    """
    assert preparers(_EMITS)["_prepare_thing_document"] == {"type", "file_path", "source_id"}
    assert "source_id" not in preparers(_MENTIONS_WITHOUT_EMITTING)["_prepare_thing_document"]


def test_the_binder_detector_separates_an_emitter_from_a_near_miss() -> None:
    assert metadata_binders(_EMITS) == {"_prepare_thing_document"}
    assert metadata_binders('def f():\n    collection_meta = {"a": 1}\n    return collection_meta\n') == set()


def test_the_inline_write_detector_sees_metadata_passed_at_the_call() -> None:
    """A writer can escape both other populations by inlining at `upsert`."""
    assert inline_write_site_keys(_INLINE_WRITE) == {"source_id", "type"}
    assert inline_write_site_keys('await c.upsert(ids=["a"], documents=[{"source_id": 1}])\n') == set()


def test_the_filter_detector_finds_keys_it_was_never_told_about() -> None:
    """The #17672 `:80` fix: no allowlist, so a NEW filter key is still found."""
    assert filter_keys(_FILTERS) == {"type", "source_id"}
    assert "$and" not in filter_keys(_FILTERS) and "$in" not in filter_keys(_FILTERS)
    assert filter_keys(_NO_FILTER) == set()
    # The property that matters: a key nobody enumerated is discovered.
    invented = 'def e(x):\n    where_filter = {"tenant_slug": x}\n    return q(where=where_filter)\n'
    assert filter_keys(invented) == {"tenant_slug"}


# ------------------------------------------------------------- the contract


def test_the_writers_emit_every_key_the_endpoints_filter_on() -> None:
    """The gap this closes is not in either side. It is between them."""
    emitted = _emitted_keys()
    filtered = _reader_filter_keys()
    assert filtered, "no endpoint filters found — re-derive the population, do not pass vacuously"

    gaps = {name: sorted(keys - emitted - set(ENGINE_SUPPLIED)) for name, keys in filtered.items()}
    gaps = {name: missing for name, missing in gaps.items() if missing}

    assert not gaps, (
        "these endpoints filter on metadata keys no writer emits, so every matching query "
        f"returns zero against rows that exist: {gaps}. writers emit: {sorted(emitted)}"
    )


def test_every_metadata_builder_is_one_the_name_based_discovery_finds() -> None:
    """Tripwire for preparer six, whatever it ends up being called."""
    unchecked = sorted(metadata_binders(_writer_source()) - set(preparers(_writer_source())))
    assert not unchecked, (
        f"these functions build a row's `metadata` but name-based discovery misses them, so the "
        f"contract never checks what they emit: {unchecked}"
    )


def test_source_id_is_emitted_by_every_preparer() -> None:
    """The specific instance, pinned so a refactor cannot quietly drop it."""
    missing = sorted(name for name, keys in preparers(_writer_source()).items() if "source_id" not in keys)
    assert not missing, (
        f"these preparers no longer emit source_id: {missing}. Rows they write cannot be reached "
        "by any per-source analytics query."
    )
