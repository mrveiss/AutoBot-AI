# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every documentation path reads ``kb_doc_set``, and no new hand-written list appears (#20063).

``DocIndexerService`` stays a curated subset of the set in its own ``autobot_docs`` collection: its
tiers order by priority and may leave files out, but may not add one the set excludes. Recorded decision on #20063.
"""

from __future__ import annotations

import ast
import glob

import pytest
from repo_tests._paths import repo_root

from autobot_shared.kb_doc_set import DOC_PATTERNS, EXCLUDE_PATTERNS, in_doc_set, should_exclude_file

_ROOT = repo_root()
_BACKEND = _ROOT / "autobot-backend"
_INDEXER = "autobot-backend/services/knowledge/doc_indexer.py"
#: Literals of this shape that are not a list of documentation to hold. The indexer's entries are
#: held inside the set by the test below.
_ALLOWED = {
    _INDEXER: "tiers: a priority order over the set",
    "autobot-backend/prompt_manager.py": "agent context files a project may carry",
    "autobot-backend/knowledge_sync_incremental.py": "which root files count as the project's, not membership",
    "autobot-backend/services/codebase_indexing_service.py": "a path prefix and a suffix",
    "autobot-backend/services/knowledge/doc_taxonomy.py": "file names read to classify a document",
    "autobot-backend/code_analysis/src/env_analyzer.py": "files the analyser skips",
}


def _doc_like(value: object) -> bool:
    return isinstance(value, str) and (value.startswith("docs/") or (value.endswith(".md") and " " not in value))


def hand_written_doc_lists(source: str) -> list[int]:
    """Lines of a list, tuple or set literal holding two or more documentation paths."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.List, ast.Tuple, ast.Set))
        and sum(isinstance(e, ast.Constant) and _doc_like(e.value) for e in node.elts) >= 2
    ]


def test_no_new_hand_written_docs_list_under_the_backend() -> None:
    paths = [p for p in _BACKEND.rglob("*.py") if "node_modules" not in p.parts and "test" not in p.name]
    assert len(paths) >= 500, f"the sweep read {len(paths)} files -- a clean result would be blind"
    found = [
        f"{p.relative_to(_ROOT).as_posix()}:{line}"
        for p in paths
        if p.relative_to(_ROOT).as_posix() not in _ALLOWED
        for line in hand_written_doc_lists(p.read_text(encoding="utf-8"))
    ]
    assert found == [], "read autobot_shared.kb_doc_set instead:\n" + "\n".join(found)


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ('X = ["docs/a.md", "docs/b.md"]', True),
        ('X = ("README.md", "CLAUDE.md")', True),
        ('X = {"docs/adr", "docs/features"}', True),
        ('X = ["docs/a.md"]', False),
        ('X = ["a", "b"]', False),
        ('X = ["see the docs.md file", "other text"]', False),
    ],
)
def test_the_list_detector_has_both_sides(source: str, flagged: bool) -> None:
    assert bool(hand_written_doc_lists(source)) is flagged


def _indexer_lists() -> dict[str, list[str]]:
    tree = ast.parse((_ROOT / _INDEXER).read_text(encoding="utf-8"))
    return {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "").startswith("TIER_")
    }


def test_every_tier_entry_is_inside_the_set() -> None:
    lists = _indexer_lists()
    assert len(lists) == 4, sorted(lists)
    outside = [f for f in lists["TIER_1_FILES"] if not in_doc_set(f)]
    outside += [d for key in lists if key != "TIER_1_FILES" for d in lists[key] if not in_doc_set(f"{d}/x.md")]
    assert outside == []


def test_membership_agrees_with_the_scan_the_sync_runs() -> None:
    """``in_doc_set`` is a second reading of the patterns, so it is held to ``glob`` over the real tree."""
    scanned = {
        hit
        for pattern in DOC_PATTERNS
        for hit in glob.glob(pattern, root_dir=_ROOT, recursive=True)
        if not should_exclude_file(f"/{hit}", EXCLUDE_PATTERNS)
    }
    assert len(scanned) >= 100, f"the scan found {len(scanned)} files"
    assert {hit for hit in scanned if not in_doc_set(hit)} == set()
    outside = {p.relative_to(_ROOT).as_posix() for p in (_ROOT / "autobot-backend").glob("*/*.md")}
    outside -= scanned
    assert outside, "no file outside the set was tried, so a set that admits everything would pass"
    assert {p for p in outside if in_doc_set(p)} == set()


@pytest.mark.parametrize(
    ("path", "member"),
    [
        ("README.md", True),
        ("docs/x.md", True),
        ("docs/a/b.md", True),
        ("autobot-backend/resources/prompts/a/b.md", True),
        ("docs/system-state.md", False),
        ("docs/node_modules/a.md", False),
        ("src/x.md", False),
        ("docs/x.txt", False),
    ],
)
def test_membership(path: str, member: bool) -> None:
    assert in_doc_set(path) is member


def test_the_retired_scan_helpers_stay_folded_into_the_indexer() -> None:
    source = (_BACKEND / "api/knowledge_population.py").read_text(encoding="utf-8")
    names = {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert not names & {"_scan_doc_files", "_process_all_doc_files", "_process_doc_file"}
    assert "get_doc_indexer_service" in source
