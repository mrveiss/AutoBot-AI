# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The knowledge-base populate script has ONE home (#19339, maintainer decision 2026-10-26).

``autobot-infrastructure/shared/scripts/populate_knowledge_base.py`` adds the project documentation
through the KB layer; ``--patterns`` covers the docs-only variant. Four copies were retired:
``populate_kb_fixed.py`` (the same flow plus an env var nothing reads), ``populate_kb_chromadb.py``
(raw writes into the KB's Chroma store, around the KB layer), ``direct_kb_populate.py`` and
``populate_docs_knowledge.py``. ``simple_populate.py`` (online, through the backend API) and
``sync_kb_docs.py`` (incremental sync) keep their own jobs but import the one documentation set.

A copy shows up as its documentation set: this guard fails when any non-test infrastructure module
other than the home spells out a pattern list holding ``docs/**/*.md``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_HOME = "autobot_shared/kb_doc_set.py"
_ENGINE = "autobot-backend/knowledge_sync_incremental.py"
_ROOTS = ("autobot-infrastructure",)
_MARKER = "docs/**/*.md"
#: A documentation glob however it is spelled: "docs/**/*.md", "docs/*.md", "docs/guides/**/*.md" ...
_DOC_GLOB = re.compile(r"^docs/.*\*.*\.md$")
_GLOB_CALLS = frozenset({"glob", "rglob", "iglob"})
#: Known copies left for their own issue (path -> the issue that retires them).
_KNOWN: dict[str, str] = {}


def _sources(root: Path) -> list[Path]:
    base = root / _ROOTS[0]
    if not base.is_dir():
        return []
    return [p for p in sorted(base.rglob("*.py")) if not p.name.endswith("_test.py") and not p.name.startswith("test_")]


REACH = declare(
    "kb-populate-doc-patterns",
    discover=_sources,
    floor=180,  # mid-window: population 189, window (170, 189)
    growth=19,  # ~10%: ordinary growth between repins must not turn an unrelated PR red
    what="non-test infrastructure Python modules",
    roots=_ROOTS,
)


def _is_md_glob_call(node: ast.AST) -> bool:
    """``docs_dir.rglob("*.md")``: a documentation set built by hand. The receiver must name a docs
    directory -- an agents/ or prompts/ directory of .md files is a different concept."""
    if not (isinstance(node, ast.Call) and node.args and isinstance(node.func, ast.Attribute)):
        return False
    first = node.args[0]
    receiver = ast.unparse(node.func.value).lower()
    return (
        node.func.attr in _GLOB_CALLS
        and isinstance(first, ast.Constant)
        and str(first.value).endswith(".md")
        and "doc" in receiver
    )


def pattern_lists(source: str, rel: str) -> list[str]:
    """Each documentation glob in *source*: a ``docs/...*.md`` string, or a glob call over ``*.md``."""
    if rel == _HOME or rel in _KNOWN:
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    return [
        f"{rel}:{node.lineno}"
        for node in ast.walk(tree)
        if (isinstance(node, ast.Constant) and isinstance(node.value, str) and _DOC_GLOB.match(node.value))
        or _is_md_glob_call(node)
    ]


def test_no_module_restates_the_documentation_set() -> None:
    files = REACH.examined(_ROOT)
    found = [h for p in files for h in pattern_lists(p.read_text(encoding="utf-8"), p.relative_to(_ROOT).as_posix())]
    REACH.completed(files)
    assert not found, f"import DOC_PATTERNS from {_HOME} (#19339): {found}"


def test_the_sync_engine_reads_the_one_documentation_set() -> None:
    source = (_ROOT / _ENGINE).read_text(encoding="utf-8")
    assert "self.doc_patterns = list(DOC_PATTERNS)" in source
    assert not pattern_lists(source, _ENGINE)


@pytest.mark.parametrize(
    "source",
    [
        'doc_patterns = ["README.md", "CLAUDE.md", "docs/**/*.md"]\n',
        'for p in ("docs/**/*.md",):\n    pass\n',
        'PATTERN = "docs/*.md"\n',
        'files = self.docs_dir.rglob("*.md")\n',
        'files = Path(docs_root).glob("**/*.md")\n',
    ],
)
def test_a_restated_documentation_set_is_flagged(source: str) -> None:
    assert pattern_lists(source, "x.py")


def test_an_agents_dir_of_md_files_is_a_different_concept() -> None:
    assert not pattern_lists('files = agents_dir.glob("*.md")\n', "x.py")


def test_the_home_and_an_import_are_not_flagged() -> None:
    assert not pattern_lists('DOC_PATTERNS = ["docs/**/*.md"]\n', _HOME)
    assert not pattern_lists("from populate_knowledge_base import DOC_PATTERNS\n", "x.py")
