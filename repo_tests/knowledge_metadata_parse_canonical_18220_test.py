# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A fact's stored metadata is parsed once, by `parse_fact_metadata` (#18220).

A raw `json.loads(<fact metadata>)` followed by `.get(...)` raises on a list, string, number or
null, which a route turns into a 500 and a batch job into an aborted run. `knowledge/search_filters.py`
(`parse_fact_metadata`, `object_metadata`) reads any stored value as a dict or skips the fact.

The detector reads the syntax tree: a `json.loads(...)` / `loads(...)` call in
`autobot-backend/api/knowledge_*.py` whose argument names fact metadata -- an identifier,
attribute or string containing "metadata" or "fact_data".

Not covered: the population is `knowledge_*.py` only, so it excludes `autobot-backend/api/knowledge.py`,
which still raw-parses fact metadata at line 2228 (`json.loads(metadata_str)`), line 2411
(`json.loads(_decode_bytes(metadata_raw, "{}"))`) and line 2501 (inside `_extract_fact_metadata`,
called at line 2578). That file is owned by the queued branch `issue-18129-doc-indexers`, so the
conversion and the widening of this guard are deferred until #18129 lands (tracked in #18220).
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_NEEDLES = ("metadata", "fact_data")


def _names_fact_metadata(arg: ast.AST) -> bool:
    for n in ast.walk(arg):
        text = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
        if text is None and isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes)):
            text = n.value if isinstance(n.value, str) else n.value.decode("utf-8", "replace")
        if text and any(needle in text for needle in _NEEDLES):
            return True
    return False


def _raw_metadata_parses(source: str) -> list[int]:
    """Line numbers of `json.loads(...)` / `loads(...)` calls whose argument names fact metadata."""
    lines = []
    for n in ast.walk(ast.parse(source)):
        if not (isinstance(n, ast.Call) and n.args):
            continue
        f = n.func
        is_loads = (isinstance(f, ast.Attribute) and f.attr == "loads") or (isinstance(f, ast.Name) and f.id == "loads")
        if is_loads and _names_fact_metadata(n.args[0]):
            lines.append(n.lineno)
    return lines


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend/api")
    except EmptyEnumeration:
        return []
    return [
        rel
        for rel in tracked
        if rel.rsplit("/", 1)[-1].startswith("knowledge_") and rel.endswith(".py") and not rel.endswith("_test.py")
    ]


REACH = declare(
    "knowledge-metadata-parse-canonical",
    discover=_population,
    # Mid-window from REACH.window(): population 46, skips 0, growth 10 -> (36, 46, 41).
    floor=41,
    what="non-test knowledge_*.py route modules",
    roots=("autobot-backend/api",),
    growth=10,
)


@functools.lru_cache(maxsize=1)
def _offenders() -> tuple[tuple[tuple[str, int], ...], int]:
    found: list[tuple[str, int]] = []
    read = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        read += 1
        found.extend((rel, line) for line in _raw_metadata_parses(source))
    REACH.completed(read)
    return tuple(sorted(found)), read


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("json.loads of a metadata name", "m = json.loads(metadata_str)\n", True),
        ("json.loads of a raw metadata name", "m = json.loads(metadata_raw) if metadata_raw else {}\n", True),
        ("json.loads of fact_data", "m = json.loads(fact_data)\n", True),
        ("a bare loads import", "m = loads(row.metadata)\n", True),
        ("json.loads of a decoded metadata expr", 'm = json.loads(d.get(b"metadata").decode())\n', True),
        ("json.loads of a job record", "job = json.loads(job_json)\n", False),
        ("json.dumps of metadata", "s = json.dumps(metadata)\n", False),
        ("the canonical parse", "m = parse_fact_metadata(fact_id, metadata_raw)\n", False),
        ("a comment naming it", "# json.loads(metadata_str)\nx = 1\n", False),
    ],
)
def test_the_matcher_tells_a_raw_metadata_parse_from_the_canonical_one(label: str, source: str, expected: bool) -> None:
    assert bool(_raw_metadata_parses(source)) is expected, label


def test_the_scan_is_not_vacuous() -> None:
    _, read = _offenders()
    assert read >= REACH.floor, f"read {read} files, below the declared floor {REACH.floor}"


def test_no_knowledge_route_parses_fact_metadata_raw() -> None:
    offenders, _ = _offenders()
    assert not offenders, (
        f"#18220: raw json.loads of fact metadata at {list(offenders)}. "
        "Use knowledge.search_filters.parse_fact_metadata (or object_metadata)."
    )
