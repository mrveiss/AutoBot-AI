# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-banned-suffix-filename — flag non-canonical version/patch file suffixes.

Module names like ``foo_v2.py``, ``foo_old.py``, ``foo_copy.py`` or
``foo_fix.py`` signal a non-canonical fork instead of editing the canonical
module in place (CLAUDE.md: no _v2/_fix suffixes). ``_fix``/``_fixed`` is
allowed on test modules (a test for a fix is legitimately named). Covers the
Python sites; non-Python (.js) coverage is a follow-up. See umbrella #10569.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-banned-suffix-filename"
ISSUE = "#10575"
# BLOCK: repo-wide scan on 2026-06-28 (post sibling-PR #10575) found 0 violations.
SEVERITY = "block"
TARGETS = ["autobot-backend", "autobot-slm-backend", "autobot_shared"]
DESCRIPTION = "Non-canonical _v2/_old/_copy/_fix file suffix — edit the canonical module in place"
FIX_HINT = "Rename to the canonical module name and fold the change into it; do not keep a suffixed fork."

_ALWAYS_BANNED = ("_v2", "_v3", "_v4", "_copy", "_old", "_new", "_backup", "_deprecated", "_orig", "_legacy")
_TEST_ONLY_BANNED = ("_fix", "_fixed")


def _banned_suffix(stem: str) -> str | None:
    for suffix in _ALWAYS_BANNED:
        if stem.endswith(suffix):
            return suffix
    is_test = stem.startswith("test_") or stem.endswith("_test")
    if not is_test:
        for suffix in _TEST_ONLY_BANNED:
            if stem.endswith(suffix):
                return suffix
    return None


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    suffix = _banned_suffix(file_path.stem)
    if suffix is None:
        return []
    return [
        Diagnostic(
            rule_id=RULE_ID,
            issue=ISSUE,
            severity=SEVERITY,
            file=file_path,
            line=1,
            col=0,
            message=f"non-canonical '{suffix}' file suffix — edit the canonical module in place",
            snippet=file_path.name,
            fix_hint=FIX_HINT,
        )
    ]
