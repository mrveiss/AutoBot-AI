# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The keys analytics endpoints FILTER on must be keys the writer EMITS (#17651).

`_prepare_problem_document` added `source_id` only ``if source_id:``. Every
codebase-analytics endpoint filters ``{"source_id": source_id}``. The two were
each internally consistent and nobody compared them, so an indexing run that
supplied no source_id wrote **11,241 rows that no per-source query could ever
match** -- present, healthy, unreachable -- and the panels rendered an honest
zero for a year's worth of scans.

This is the fourth instance of the shape in one day (#17643 was the third: a
frontend filtering on event names the backend never emits). What they share is
that both sides are correct in isolation; the defect lives only in the gap, so
no test of either side can see it. That is what this file is for.
"""

from __future__ import annotations

import ast
import re

from repo_tests._paths import repo_root

_ANALYTICS = repo_root() / "autobot-backend" / "api" / "codebase_analytics"
_WRITER = _ANALYTICS / "chromadb_storage.py"

#: Keys a reader may filter on that the problem writer is not expected to emit.
#: Chroma's own document key is supplied by the engine, not by our metadata.
_ENGINE_SUPPLIED = {"chroma:document"}


def _preparers() -> dict[str, set[str]]:
    """Every `_prepare_*_document` function, mapped to the metadata keys it emits.

    ALL of them, not one. The first version of this guard inspected only
    `_prepare_problem_document` and passed -- while `_prepare_function_document`,
    `_prepare_class_document`, `_prepare_import_document` and
    `_prepare_stats_document` carry the identical conditional and were
    unexamined. A guard that names "the writer" and sees one of five is the same
    defect it was written to catch, so the population is discovered rather than
    listed.

    Parsed, not grepped: a key named in a docstring is not a key that is written,
    and telling those apart is the whole job.
    """
    tree = ast.parse(_WRITER.read_text(encoding="utf-8"))
    found: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not (node.name.startswith("_prepare_") and node.name.endswith("_document")):
            continue
        keys: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Dict):
                keys |= {k.value for k in sub.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Constant):
                if isinstance(sub.slice.value, str):
                    keys.add(sub.slice.value)
        found[node.name] = keys
    assert found, "no _prepare_*_document functions found — re-derive, do not pass vacuously"
    return found


def _emitted_metadata_keys() -> set[str]:
    """The union of keys every preparer emits."""
    return set().union(*_preparers().values())


def _filtered_keys() -> dict[str, set[str]]:
    """Metadata keys each endpoint module uses in a Chroma `where` filter."""
    found: dict[str, set[str]] = {}
    for path in sorted((_ANALYTICS / "endpoints").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        # {"key": {"$in": [...]}} and {"key": value} inside a where filter
        keys = set(re.findall(r'\{\s*"([a-z_]+)"\s*:\s*\{?\s*"?\$?', text))
        keys &= {"source_id", "type", "problem_type", "severity", "file_path", "file_category"}
        if keys:
            found[path.name] = keys
    return found


def test_the_writer_emits_every_key_the_endpoints_filter_on() -> None:
    """The gap this closes is not in either side. It is between them."""
    emitted = _emitted_metadata_keys()
    filtered = _filtered_keys()
    assert filtered, "no endpoint filters found — re-derive the population, do not pass vacuously"

    gaps = {name: sorted(keys - emitted - _ENGINE_SUPPLIED) for name, keys in filtered.items()}
    gaps = {name: missing for name, missing in gaps.items() if missing}

    assert not gaps, (
        "these endpoints filter on metadata keys the problem writer never emits, so every "
        f"matching query returns zero against rows that exist: {gaps}. "
        f"writer emits: {sorted(emitted)}"
    )


def test_source_id_is_among_the_emitted_keys() -> None:
    """The specific instance, pinned so a refactor cannot quietly drop it again.

    `source_id` is emitted conditionally (`if source_id:`), which is why the
    general test above cannot be the whole guard: the key appears in the source
    either way. What this asserts is that the writer still knows about it at
    all -- removing the assignment is the regression that recreates #17651.
    """
    missing = sorted(name for name, keys in _preparers().items() if "source_id" not in keys)
    assert not missing, (
        f"these document preparers no longer emit source_id at all: {missing}. "
        "Rows they write cannot be reached by any per-source analytics query."
    )
