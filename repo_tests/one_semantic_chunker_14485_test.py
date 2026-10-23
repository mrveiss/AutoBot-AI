# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One semantic chunker family (#14485).

Owner decision 2026-10-10: the canonical chunker is `SemanticChunkerBase` with its CPU
(`utils/semantic_chunker.py`) and GPU (`utils/semantic_chunker_gpu.py`) subclasses; both stay.
The ingest pipeline's token-budget chunker is the second fork: its algorithm now lives in
`utils/token_budget_chunking.py`, and its class becomes a thin adapter after #17855 merges.

Two markers, both read from the syntax tree so prose naming them is not a definition:
a class named `...SemanticChunker` or deriving from `SemanticChunkerBase` outside the
canonical modules, and a `@TaskRegistry.register_extractor("chunk_text")` registration count.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = (
    "autobot-backend/utils/semantic_chunker.py",
    "autobot-backend/utils/semantic_chunker_base.py",
    "autobot-backend/utils/semantic_chunker_gpu.py",
)
_BASE = "SemanticChunkerBase"
_SUFFIX = "SemanticChunker"
_REGISTRATION = "chunk_text"

#: Dated, issue-tied exemption: the pipeline's chunker class still exists because its file is
#: owned by an unmerged branch. Not permanent -- `test_the_pending_entry_is_not_stale` fails
#: the moment the class is gone, and the entry must then be deleted.
_PENDING_ADAPTER = {
    "autobot-backend/knowledge/pipeline/extractors/semantic_chunker.py": (
        "#14485 adapter lands after #17855 merges (2026-10-10)"
    ),
}


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else ""


def _chunker_classes(source: str) -> list[str]:
    """Names of classes called `...SemanticChunker`, `SemanticChunkerBase`, or deriving from it."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef):
            if node.name.endswith(_SUFFIX) or node.name == _BASE or any(_base_name(b) == _BASE for b in node.bases):
                found.append(node.name)
    return found


def _is_chunk_text_registration(dec: ast.expr) -> bool:
    return (
        isinstance(dec, ast.Call)
        and isinstance(dec.func, ast.Attribute)
        and dec.func.attr == "register_extractor"
        and bool(dec.args)
        and isinstance(dec.args[0], ast.Constant)
        and dec.args[0].value == _REGISTRATION
    )


def _chunk_text_registrations(source: str) -> int:
    """How many decorated definitions register the `chunk_text` extractor."""
    return sum(
        1
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_chunk_text_registration(d) for d in node.decorator_list)
    )


def _is_source_python(rel: str) -> bool:
    """A non-test Python file: the only kind that can be a second chunker."""
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("autobot-backend/utils/semantic_chunker.py", True),
        ("autobot-backend/utils/semantic_chunker_test.py", False),
        ("autobot-backend/tests/test_chunker.py", False),
        ("autobot-backend/knowledge/test_chunker.py", False),
        ("autobot-backend/utils/notes.md", False),
    ],
)
def test_the_test_path_filter_skips_tests_and_keeps_source(rel: str, expected: bool) -> None:
    assert _is_source_python(rel) is expected


def _source_population(root: Path) -> list[str]:
    """Non-test Python source in the backend and autobot_shared: the scan's whole input."""
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "semantic-chunker-fork-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=2702,
    what="non-test python source",
    roots=("autobot-backend", "autobot_shared"),
    growth=300,
)


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[dict[str, list[str]], dict[str, int], int]:
    """Chunker classes per file, `chunk_text` registrations per file, and files parsed."""
    classes: dict[str, list[str]] = {}
    registrations: dict[str, int] = {}
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = _read(rel)
        if _SUFFIX not in source and _REGISTRATION not in source:
            continue
        parsed += 1
        if found := _chunker_classes(source):
            classes[rel] = found
        if count := _chunk_text_registrations(source):
            registrations[rel] = count
    return classes, registrations, parsed


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a fork named for the idea", "class FooSemanticChunker:\n    pass\n", ["FooSemanticChunker"]),
        ("a bare name", "class SemanticChunker(Base):\n    pass\n", ["SemanticChunker"]),
        ("a subclass of the base", "class Whatever(SemanticChunkerBase):\n    pass\n", ["Whatever"]),
        ("a qualified base", "class W(m.SemanticChunkerBase):\n    pass\n", ["W"]),
        ("a second base", "class SemanticChunkerBase(ABC):\n    pass\n", ["SemanticChunkerBase"]),
        ("a comment", "# class FooSemanticChunker:\nx = 1\n", []),
        ("a string literal", 's = "class FooSemanticChunker:"\n', []),
        ("an unrelated class", "class Splitter:\n    pass\n", []),
        ("a reference, not a definition", "x = FooSemanticChunker()\n", []),
    ],
)
def test_the_matcher_tells_a_chunker_class_from_a_mention(label: str, source: str, expected: list[str]) -> None:
    assert _chunker_classes(source) == expected, label


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a class registration", '@TaskRegistry.register_extractor("chunk_text")\nclass A:\n    pass\n', 1),
        ("a function registration", '@R.register_extractor("chunk_text")\ndef f():\n    pass\n', 1),
        ("another task", '@TaskRegistry.register_extractor("extract_pdf")\nclass A:\n    pass\n', 0),
        ("a comment", '# @TaskRegistry.register_extractor("chunk_text")\nclass A:\n    pass\n', 0),
        ("a string literal", "s = 'register_extractor(\"chunk_text\")'\n", 0),
    ],
)
def test_the_matcher_counts_chunk_text_registrations(label: str, source: str, expected: int) -> None:
    assert _chunk_text_registrations(source) == expected, label


def test_the_scan_is_not_vacuous() -> None:
    """The canonical modules must be found: the base and both subclasses define chunker classes."""
    classes, _, parsed = _scan()
    assert parsed >= 4, f"parsed {parsed} files mentioning a chunker"
    missing = [rel for rel in _CANONICAL if rel not in classes]
    assert not missing, f"the scan did not find the canonical chunker modules: {missing}"


def test_no_second_semantic_chunker_family() -> None:
    classes, _, _ = _scan()
    allowed = set(_CANONICAL) | set(_PENDING_ADAPTER)
    forks = {rel: names for rel, names in classes.items() if rel not in allowed}
    assert not forks, (
        f"#14485: chunker classes outside the canonical family: {forks}. Extend "
        "`SemanticChunkerBase` (utils/semantic_chunker_base.py) or add a strategy to "
        "utils/token_budget_chunking.py instead of writing another chunker."
    )


def test_exactly_one_chunk_text_extractor_is_registered() -> None:
    _, registrations, _ = _scan()
    assert sum(registrations.values()) == 1, f"#14485: chunk_text registered in {registrations}; expected one"


def test_the_pending_entry_is_not_stale() -> None:
    """Each exempt file must still define the class; once it does not, delete the entry."""
    classes, _, _ = _scan()
    stale = [rel for rel in _PENDING_ADAPTER if rel not in classes]
    assert not stale, f"#14485: {stale} no longer define a chunker class; remove them from _PENDING_ADAPTER"
