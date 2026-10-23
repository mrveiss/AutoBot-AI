# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One documentation-indexing pipeline (#18129).

Documentation indexing had three implementations: `DocIndexerService` and two standalone
scripts under `autobot-infrastructure/shared/` that re-derived front matter, tags and
chunking. The scripts are now shims over `tools/index_documentation.py`, which resolves the
service. This guard fails when a further module grows its own markdown chunker.

The marker is a markdown-HEADING SPLIT: a `re.split(...)` / `.split(...)` call whose first
argument is a string constant naming `##` or `#{n}` heading syntax. A chunker has to cut on
headings, so a pipeline cannot avoid it; a module that merely tests one line for a heading
(`re.match`) is not a chunker. The detector reads the syntax tree, so a comment or docstring
mentioning the pattern is not a definition.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: The service owns the pipeline; the shared helper is the section splitter it calls.
_ALLOWED = {
    "autobot-backend/services/knowledge/doc_indexer.py",
    "autobot_shared/doc_chunking.py",
}
_ENTRY_POINT = "tools/index_documentation.py"
_SHIMS = (
    "autobot-infrastructure/shared/tools/index_documentation.py",
    "autobot-infrastructure/shared/scripts/utilities/index_documentation.py",
)
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared", "autobot-infrastructure", "tools", "scripts")


def _is_heading_pattern(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and ("##" in node.value or "#{" in node.value)


def _splits_markdown_headings(source: str) -> bool:
    """True when `source` calls a `split` whose first argument is a heading pattern."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "split":
            if node.args and _is_heading_pattern(node.args[0]):
                return True
    return False


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "one-doc-indexer",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=3392,  # re-pinned mid-window (train 58): population 3542, window [3242, 3542]
    what="non-test python source",
    roots=_ROOTS,
    growth=300,
)


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _chunkers() -> tuple[tuple[str, ...], int]:
    """Files that split markdown on headings, and how many were parsed."""
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = _read(rel)
        if "#" not in source:
            continue
        parsed += 1
        if _splits_markdown_headings(source):
            found.append(rel)
    return tuple(found), parsed


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a regex heading split", 'import re\nre.split(r"^(##\\s+.+)$", text)\n', True),
        ("the retired script's split", 'import re\nre.split(r"\\n(#{1,3}\\s+.+)\\n", text)\n', True),
        ("a str.split on a heading", 'text.split("\\n## ")\n', True),
        ("a one-line heading test", 'import re\nre.match(r"^#{1,6}\\s+", line)\n', False),
        ("a split on commas", 'x.split(",")\n', False),
        ("a docstring naming it", '"""re.split(r"^(##\\s+.+)$", t)"""\nx = 1\n', False),
    ],
)
def test_the_matcher_tells_a_chunker_from_a_heading_test(label: str, source: str, expected: bool) -> None:
    assert _splits_markdown_headings(source) is expected, label


def test_the_scan_is_not_vacuous() -> None:
    """The service and the shared splitter both cut on headings; fewer is a blind scan."""
    found, parsed = _chunkers()
    assert set(found) >= _ALLOWED, f"expected {sorted(_ALLOWED)} among {list(found)} ({parsed} parsed)"


def test_only_the_canonical_service_chunks_markdown() -> None:
    extra = sorted(set(_chunkers()[0]) - _ALLOWED)
    assert not extra, (
        f"#18129: {extra} split markdown on headings; documentation indexing lives once in "
        f"{sorted(_ALLOWED)}. Call DocIndexerService (via {_ENTRY_POINT}) instead of copying its chunker."
    )


def test_the_entry_point_resolves_the_service_and_the_shims_run_it() -> None:
    assert "get_doc_indexer_service" in _read(_ENTRY_POINT)
    for rel in _SHIMS:
        source = _read(rel)
        assert "runpy.run_path" in source and "index_documentation.py" in source, rel
        assert len(source.splitlines()) < 40, f"{rel} is no longer a thin shim"
