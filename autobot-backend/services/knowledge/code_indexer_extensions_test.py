# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The indexer's notion of "source" comes from the canonical registry (#13510).

Two defects, one cause. ``_EXTRACTORS`` restated its own extension list instead of
consuming ``utils/file_categorization``, so the indexer's idea of indexable source
drifted from the platform's idea of source code. And files outside that literal list
were filtered out during collection, *before* any counter saw them — so they could
not appear in ``files_scanned`` or in ``skipped`` either. They were invisible, not
merely absent, and a partially covered graph reported itself as complete.
"""

import asyncio
from pathlib import Path

import pytest

from services.knowledge.code_indexer import (
    _EXTRACTORS,
    _NO_GRAMMAR_EXTENSIONS,
    UNSUPPORTED_CODE_EXTENSIONS,
    CodeIndexer,
    extract_javascript,
    extract_python,
)
from utils.file_categorization import (
    ALL_CODE_EXTENSIONS,
    JS_EXTENSIONS,
    PYTHON_EXTENSIONS,
    TS_EXTENSIONS,
    VUE_EXTENSIONS,
)

# ----------------------------------------------------- derived, not restated


@pytest.mark.parametrize("ext", sorted(JS_EXTENSIONS | TS_EXTENSIONS | VUE_EXTENSIONS))
def test_every_js_family_extension_has_an_extractor(ext):
    """``.mjs``/``.cjs``/``.mts``/``.cts`` were absent from the old literal map."""
    assert _EXTRACTORS.get(ext) is extract_javascript


@pytest.mark.parametrize("ext", sorted(PYTHON_EXTENSIONS - _NO_GRAMMAR_EXTENSIONS))
def test_every_parseable_python_extension_has_an_extractor(ext):
    assert _EXTRACTORS.get(ext) is extract_python


def test_cython_is_held_back_deliberately():
    """Deriving blindly would map Cython onto the Python grammar.

    Measured: tree-sitter-python reads a file declaring ``cdef add``, ``cpdef scale``
    and ``def normal`` as containing only ``normal``. The cdef definitions vanish
    while calls to them survive as unresolvable edges — worse than not indexing the
    file, which is the exact trade the issue warns about for ``.mjs``.
    """
    assert _NO_GRAMMAR_EXTENSIONS <= PYTHON_EXTENSIONS
    for ext in _NO_GRAMMAR_EXTENSIONS:
        assert ext not in _EXTRACTORS


def test_cython_shows_up_as_unsupported_rather_than_unknown():
    """Held back is not the same as unheard of — these must still be counted."""
    for ext in _NO_GRAMMAR_EXTENSIONS:
        assert ext in UNSUPPORTED_CODE_EXTENSIONS


def test_the_two_sets_partition_the_canonical_registry():
    """Every code extension is either extractable or explicitly unsupported.

    The property that makes the counting honest: nothing the platform calls code can
    fall outside both sets and so escape both the index and the skip tally.
    """
    covered = frozenset(_EXTRACTORS) | UNSUPPORTED_CODE_EXTENSIONS

    assert frozenset(ALL_CODE_EXTENSIONS) <= covered
    assert not (frozenset(_EXTRACTORS) & UNSUPPORTED_CODE_EXTENSIONS)


def test_unsupported_is_not_empty():
    """Guard the guard: an empty set would make the counting tests vacuous."""
    assert UNSUPPORTED_CODE_EXTENSIONS


# --------------------------------------------------- collection counts, not drops


def _collect(tmp_path: Path):
    return asyncio.run(CodeIndexer._collect_source_files(str(tmp_path)))


def test_module_javascript_is_collected(tmp_path):
    """The live half of the coverage hole: ``.mjs``/``.cjs`` were never collected."""
    (tmp_path / "esm.mjs").write_text("export function a() {}\n", encoding="utf-8")
    (tmp_path / "cjs.cjs").write_text("function b() {}\nmodule.exports = { b };\n", encoding="utf-8")

    found, unsupported = _collect(tmp_path)

    assert sorted(p.name for p in found) == ["cjs.cjs", "esm.mjs"]
    assert unsupported == []


def test_code_with_no_extractor_is_returned_for_counting(tmp_path):
    """Previously dropped mid-walk, so no counter could ever see it."""
    (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")
    (tmp_path / "lib.rs").write_text("fn main() {}\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("def f():\n    pass\n", encoding="utf-8")

    found, unsupported = _collect(tmp_path)

    assert [p.name for p in found] == ["app.py"]
    assert sorted(p.name for p in unsupported) == ["lib.rs", "main.go"]


def test_non_code_files_are_neither_indexed_nor_counted(tmp_path):
    """Skipped-unsupported must mean "code we cannot read", not "every other file"."""
    (tmp_path / "notes.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "photo.png").write_bytes(b"\x89PNG")

    found, unsupported = _collect(tmp_path)

    assert found == []
    assert unsupported == []


def test_a_root_under_a_hidden_directory_still_collects(tmp_path):
    """Found while measuring this change: the walk tested the *absolute* path.

    ``path.parts`` includes every component above *root*, so the hidden-directory
    rule matched things the caller never asked about — a checkout under
    ``.worktrees/``, a ``.cache`` ancestor, a dotted home directory — and the walk
    returned nothing at all. Silent: an index run over such a root reported success
    having read zero files.
    """
    root = tmp_path / ".hidden_parent" / "project"
    root.mkdir(parents=True)
    (root / "app.py").write_text("def f():\n    pass\n", encoding="utf-8")
    (root / "vendor.go").write_text("package main\n", encoding="utf-8")

    found, unsupported = _collect(root)

    assert [p.name for p in found] == ["app.py"]
    assert [p.name for p in unsupported] == ["vendor.go"]


def test_hidden_directories_below_root_are_still_skipped(tmp_path):
    """The rule it was meant to enforce must survive the fix."""
    hidden = tmp_path / ".git"
    hidden.mkdir()
    (hidden / "hook.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")

    found, _ = _collect(tmp_path)

    assert [p.name for p in found] == ["app.py"]


def test_vendor_directories_are_still_skipped(tmp_path):
    """The new branch must not resurrect third-party code as "unsupported"."""
    vendor = tmp_path / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "index.mjs").write_text("export const x = 1;\n", encoding="utf-8")
    (vendor / "native.go").write_text("package main\n", encoding="utf-8")

    found, unsupported = _collect(tmp_path)

    assert found == []
    assert unsupported == []
