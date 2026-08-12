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

# The extraction measurements below need the grammar; the set-derivation tests do
# not. Mirrors the probe in ``code_indexer_test.py`` — CI's python-suite venv does
# not install tree-sitter, which is how the unmarked version of this file went red.
tree_sitter_available = True
try:
    import tree_sitter_python  # noqa: F401
except ImportError:
    tree_sitter_available = False

requires_tree_sitter = pytest.mark.skipif(not tree_sitter_available, reason="tree-sitter-python not installed")

from autobot_shared.code_graph import module_path_from_rel_path
from services.knowledge.code_indexer import (
    _COLLIDING_STUB_EXTENSIONS,
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


@pytest.mark.parametrize("ext", sorted(PYTHON_EXTENSIONS - _NO_GRAMMAR_EXTENSIONS - _COLLIDING_STUB_EXTENSIONS))
def test_every_parseable_python_extension_has_an_extractor(ext):
    assert _EXTRACTORS.get(ext) is extract_python


@requires_tree_sitter
def test_cython_is_held_back_deliberately():
    """Deriving blindly would map Cython onto the Python grammar.

    The measurement is *run here* rather than described in a comment: a claim a test
    only asserts in prose stops being true the moment the grammar changes, and
    nothing notices.
    """
    assert _NO_GRAMMAR_EXTENSIONS <= PYTHON_EXTENSIONS
    for ext in _NO_GRAMMAR_EXTENSIONS:
        assert ext not in _EXTRACTORS

    cython = b"cdef int add(int a, int b):\n    return a + b\n\ndef normal(y):\n    return add(y, 1)\n"
    extracted = extract_python("x.pyx", cython)

    # Checked before the interesting assertion so its message cannot misdiagnose:
    # with no grammar installed, extraction returns zero nodes, which would read as
    # "the parser stopped seeing cdef" when the parser was never there.
    assert not extracted.get("dep_error"), extracted.get("dep_error")

    names = {n.get("name") for n in extracted["nodes"]}
    assert names == {"normal"}, f"tree-sitter-python now reads cdef ({sorted(names)}) — reconsider the holdback"
    assert extracted["edges"], "the call to the invisible cdef survives as a dangling edge"


def test_python_stubs_are_held_back_over_node_identity_not_grammar():
    """``foo.py`` and ``foo.pyi`` compute the same node ids, so the stub would win.

    A different reason from Cython's, kept in a different constant: the grammar reads
    stubs perfectly. It is ``module_path_from_rel_path`` stripping the suffix that
    makes them indistinguishable. See #13824.
    """
    assert _COLLIDING_STUB_EXTENSIONS <= PYTHON_EXTENSIONS
    assert not (_COLLIDING_STUB_EXTENSIONS & _NO_GRAMMAR_EXTENSIONS)
    for ext in _COLLIDING_STUB_EXTENSIONS:
        assert ext not in _EXTRACTORS
        assert ext in UNSUPPORTED_CODE_EXTENSIONS

    assert module_path_from_rel_path("pkg/foo.pyi") == module_path_from_rel_path("pkg/foo.py")


def test_every_extension_the_walk_can_match_is_lowercase():
    """The walk matches on ``suffix.lower()``, so an uppercase member matches nothing.

    ``ALL_CODE_EXTENSIONS`` carries ``.R``/``.Rmd``/``.S``. Left uncased they would sit
    in the unsupported set and never fire — invisible again, which is this issue.
    """
    for ext in UNSUPPORTED_CODE_EXTENSIONS | frozenset(_EXTRACTORS):
        assert ext == ext.lower(), ext


def test_cython_shows_up_as_unsupported_rather_than_unknown():
    """Held back is not the same as unheard of — these must still be counted."""
    for ext in _NO_GRAMMAR_EXTENSIONS:
        assert ext in UNSUPPORTED_CODE_EXTENSIONS


def test_the_indexer_never_claims_an_extension_the_registry_does_not_call_code():
    """The one direction that is not set algebra.

    "Every code extension is covered by one set or the other" holds for *any*
    `_EXTRACTORS` whatsoever, because `UNSUPPORTED_CODE_EXTENSIONS` is defined as the
    complement — asserting it proves nothing about this map. The containment that can
    actually fail is the other way round: an extractor registered for something the
    canonical registry does not classify as code, which would mean the two have
    drifted apart again in the opposite direction.
    """
    registry = frozenset(ext.lower() for ext in ALL_CODE_EXTENSIONS)
    stray = frozenset(_EXTRACTORS) - registry

    assert stray == frozenset(), f"extractors for extensions the registry does not call code: {sorted(stray)}"


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


# ------------------------------------------- what index_directory actually reports


class _StubIndexer(CodeIndexer):
    """Drives ``index_directory``'s counting without ChromaDB or a hash cache."""

    def __init__(self, cache_file):
        self._cache_file = cache_file
        self._hash_cache = {}
        self._known_ids = set()

    def _load_cache(self):
        return {}

    async def _seed_known_ids_from_collection(self):
        return set()

    async def index_file(self, path, root_dir=None, force=False):
        from services.knowledge.code_indexer import CodeIndexResult

        return CodeIndexResult(success=1)


def test_index_directory_reports_the_files_it_could_not_read(tmp_path):
    """The production-facing half of the fix, and the part nothing else covers.

    Collection returning the unsupported list is inert unless ``index_directory``
    folds it into the result — which is what a consumer reads. Without this test the
    counting branch could be deleted and only the collection unit tests would notice.
    """
    (tmp_path / "app.py").write_text("def f():\n    pass\n", encoding="utf-8")
    (tmp_path / "run.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (tmp_path / "deploy.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# hi\n", encoding="utf-8")

    result = asyncio.run(_StubIndexer(tmp_path / "cache.json").index_directory(str(tmp_path)))

    assert result.success == 1, "the one indexable file was not indexed"
    assert result.skipped == 3, "the three unreadable code files were not counted"
    assert result.unsupported_extensions == {".sh": 2, ".go": 1}
    assert ".md" not in result.unsupported_extensions, "a non-code file leaked into the coverage report"


def test_index_directory_reports_nothing_when_everything_was_readable(tmp_path):
    """An empty report must mean full coverage, not an absent one."""
    (tmp_path / "app.py").write_text("def f():\n    pass\n", encoding="utf-8")

    result = asyncio.run(_StubIndexer(tmp_path / "cache.json").index_directory(str(tmp_path)))

    assert result.unsupported_extensions == {}
    assert result.skipped == 0


def test_vendor_directories_are_still_skipped(tmp_path):
    """The new branch must not resurrect third-party code as "unsupported"."""
    vendor = tmp_path / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "index.mjs").write_text("export const x = 1;\n", encoding="utf-8")
    (vendor / "native.go").write_text("package main\n", encoding="utf-8")

    found, unsupported = _collect(tmp_path)

    assert found == []
    assert unsupported == []
