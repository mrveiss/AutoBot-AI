# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Regression test: indexing endpoint resolves clone path via source_paths (#11129).

Guards against the ImportError that occurred when ``_make_clone_path`` was removed
from ``endpoints/sources.py`` (the Task-2 dedupe) but ``endpoints/indexing.py`` still
imported it from there. The fix imports the PUBLIC ``make_clone_path`` from
``api.codebase_analytics.source_paths``.

These checks are intentionally lightweight / static: fully importing
``endpoints/indexing.py`` pulls a heavy chain (``knowledge.backends``, scanner,
chromadb) whose availability depends on which other test suite's conftest stubs are
active in the session — so an import-based test is order-dependent and flaky in the
full suite. A source-level check catches exactly the stale-import regression without
that fragility.
"""
import ast
from pathlib import Path

_INDEXING = Path(__file__).parent / "endpoints" / "indexing.py"


def test_make_clone_path_importable_from_source_paths():
    """The public helper must live in source_paths and produce a code-sources path."""
    from api.codebase_analytics.source_paths import make_clone_path

    result = make_clone_path("abc123")
    assert result.endswith("abc123"), f"Unexpected path: {result}"
    assert "code-sources" in result


def test_indexing_does_not_reference_removed_private_helper():
    """indexing.py must not import/use the deleted ``_make_clone_path``."""
    src = _INDEXING.read_text(encoding="utf-8")
    assert "_make_clone_path" not in src, (
        "endpoints/indexing.py still references the removed _make_clone_path; "
        "it must use make_clone_path from api.codebase_analytics.source_paths (#11129)"
    )


def test_indexing_imports_public_make_clone_path_from_source_paths():
    """indexing.py must import ``make_clone_path`` from the shared source_paths module."""
    tree = ast.parse(_INDEXING.read_text(encoding="utf-8"))
    imports_it = any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "").endswith("source_paths")
        and any(alias.name == "make_clone_path" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert imports_it, "indexing.py must `from ..source_paths import make_clone_path` (#11129)"
