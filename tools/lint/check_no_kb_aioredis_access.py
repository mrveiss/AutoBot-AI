#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression-prevention check for the #5225 KB redis accessor migration.

Blocks two banned patterns so new code keeps going through the
``KnowledgeBase.redis()`` public accessor (introduced in #5184 / PR #5218)
instead of reaching into KB internals:

  1. Any reference to ``aioredis_client`` (the *old* public attribute name)
     outside the allowlisted files. The attribute was renamed to
     ``_aioredis_client`` in #5225 after all 159 external call sites were
     migrated to ``KB.redis()`` (PRs #5252, #5261, #5272, #5293). The old
     name must never reappear.

  2. Any reference to the private ``_aioredis_client`` attribute from
     outside the KB class itself. Inside ``knowledge/base.py`` the
     attribute is legitimately accessed by the accessor and the
     bootstrap/shutdown paths; the sibling mixin files declare a
     class-level type hint; init-state test files construct fake KB
     instances that set or read the attribute. All other call sites must
     go through ``kb.redis()``.

Use ``kb.redis()`` instead — it raises ``RuntimeError`` if the KB is not
yet initialized, matching the contract the 159 migrated call sites rely on.

Exit code:
  0 — clean (no banned patterns found in scanned files)
  1 — banned patterns found (PR/commit blocked)
  2 — usage error
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

# tools/lint/ is not a Python package; ensure sibling module is importable
# regardless of invocation mode (script / importlib from tests).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import iter_python_files  # noqa: E402

# Files allowed to reference the attribute directly.
#
# Why each entry is here (POSIX-normalized paths relative to repo root):
#
#  * ``tools/lint/check_no_kb_aioredis_access.py`` — this hook contains
#    the patterns as strings.
#  * ``autobot-backend/knowledge/base.py`` — KB class body: declares the
#    attribute, implements ``redis()``, and has three lifecycle sites
#    (init-connect, cleanup-on-failure, close) that legitimately bypass
#    ``redis()`` because they run before/after the initialized contract.
#  * ``autobot-backend/knowledge/{bulk,categories,collections,facts,
#    metadata,relations,search,stats,suggestions,tags,versioning}.py`` —
#    sibling KB mixins that declare class-level type hints for the
#    attribute (``_aioredis_client: "aioredis.Redis"``). They never *read*
#    the attribute — all method-body access goes through ``self.redis()``.
#  * Test files that construct fake KB instances or make init-state
#    assertions. These legitimately set ``kb._aioredis_client = ...`` or
#    check ``kb._aioredis_client is None``.
ALLOWLIST = {
    # The hook itself.
    "tools/lint/check_no_kb_aioredis_access.py",
    # KB class body + sibling mixins (type hints only).
    "autobot-backend/knowledge/base.py",
    "autobot-backend/knowledge/bulk.py",
    "autobot-backend/knowledge/categories.py",
    "autobot-backend/knowledge/collections.py",
    "autobot-backend/knowledge/facts.py",
    "autobot-backend/knowledge/metadata.py",
    "autobot-backend/knowledge/relations.py",
    "autobot-backend/knowledge/search.py",
    "autobot-backend/knowledge/stats.py",
    "autobot-backend/knowledge/suggestions.py",
    "autobot-backend/knowledge/tags.py",
    "autobot-backend/knowledge/versioning.py",
    # Tests that construct fake KB instances or assert init state.
    "autobot-backend/tests/test_knowledge_boards.py",
    "autobot-backend/tests/knowledge/test_facts_dedup.py",
    "autobot-backend/knowledge/knowledge_base_async_test.py",
    "autobot-backend/knowledge/knowledge_base.integration_test.py",
    "autobot-backend/utils/stats_counter_parsing_test.py",
    "autobot-backend/api/knowledge_audit_test.py",
    # Pre-existing string-literal-in-source assertion (Pattern D, #5225).
    "autobot-backend/api/api_endpoint_migrations_test.py",
}

# Patterns — precise to avoid matching unrelated tokens like
# ``aioredis_client=kb.redis()`` (kwargs) or ``aioredis_client`` as a
# function parameter name (legitimate in knowledge_collaboration.py).
#
# The patterns target attribute access (``.aioredis_client`` /
# ``._aioredis_client``), which is the specific coupling we want to
# prevent.
PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    (
        "kb-public-aioredis-client",
        # Attribute access: ``<obj>.aioredis_client`` with NOT an
        # underscore before the identifier — we want to catch the old
        # public name but NOT the new private ``._aioredis_client``.
        # Negative lookbehind ``(?<!_)`` excludes the private name;
        # the leading ``\.`` ensures we only match attribute access
        # (not bare identifiers like function parameters).
        re.compile(r"\.(?<!_)aioredis_client\b"),
        "Use `kb.redis()` instead. The public `aioredis_client` attribute "
        "was renamed to `_aioredis_client` in #5225 — all call sites must "
        "go through the `KB.redis()` accessor.",
    ),
    (
        "kb-private-aioredis-client",
        # Attribute access to the private name from outside the KB class.
        # Allowlisted files (KB class, mixins, test fakes) are filtered
        # before regex scan, so hits here mean a NEW caller reached into
        # the private attribute.
        re.compile(r"\._aioredis_client\b"),
        "Use `kb.redis()` instead. `_aioredis_client` is private to the "
        "`KnowledgeBase` class (#5225) — external callers must go through "
        "the public `redis()` accessor.",
    ),
]


def _is_allowlisted(rel_path: str) -> bool:
    """Check if a file path is in the allowlist (POSIX-normalized)."""
    posix = rel_path.replace("\\", "/")
    return posix in ALLOWLIST


def _scan(path: Path, repo_root: Path) -> List[Tuple[int, str, str]]:
    """Return [(line_no, pattern_id, message)] of banned-pattern hits."""
    try:
        rel = str(path.resolve().relative_to(repo_root))
    except ValueError:
        # Path is outside the repo (e.g. /tmp test files) — scan as-is
        rel = str(path)
    if _is_allowlisted(rel):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits: List[Tuple[int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern_id, regex, message in PATTERNS:
            if regex.search(line):
                hits.append((line_no, pattern_id, message))
    return hits


def main(argv: List[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    files = list(iter_python_files(argv[1:], repo_root))
    total_hits = 0
    for path in files:
        for line_no, pattern_id, message in _scan(path, repo_root):
            try:
                rel = path.resolve().relative_to(repo_root)
            except ValueError:
                rel = path
            print(
                f"[no-kb-aioredis-access] {rel}:{line_no}: {pattern_id} — {message}",
                file=sys.stderr,
            )
            total_hits += 1
    if total_hits:
        print(
            f"\n[no-kb-aioredis-access] {total_hits} banned pattern(s) found. "
            f"Use `kb.redis()` instead of reaching into KB internals (#5225).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
