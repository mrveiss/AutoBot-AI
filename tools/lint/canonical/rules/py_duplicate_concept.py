# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-duplicate-concept — flag Enhanced/Unified/Consolidated era-marker names.

An ``EnhancedFoo`` / ``UnifiedFoo`` / ``ConsolidatedFoo`` name is canonical-debt:
instead of extending the original concept in place, a prefixed (or infixed) fork
was created. This fires on the banned era-marker token appearing anywhere in a
class OR function name — **prefix, infix, or standalone** — not only when a base
concept coexists in the same file. That closes the gap where infix names like
``AIStackEnhancedSearchData`` or ``KnowledgeUnifiedSearchResponse`` slipped past
the old prefix-anchored check (audit gap on #10746).

BLOCK severity — the backend / slm-backend / autobot_shared **production** source
is clean of these tokens (verified #10746), so any new occurrence must be renamed
to a descriptive canonical name (never a synonym like Advanced/Aggregated). Test
files are out of scope: migration / back-compat tests legitimately reference the
old names by design. Git's ``unified diff`` format term is allow-listed.
See canonical-debt umbrella #10569.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-duplicate-concept"
ISSUE = "#10577"
SEVERITY = "block"
TARGETS = ["autobot-backend", "autobot-slm-backend", "autobot_shared"]
DESCRIPTION = "Enhanced/Unified/Consolidated era-marker in a class/function name — rename to the canonical concept"
FIX_HINT = (
    "Rename the Enhanced/Unified/Consolidated name to the plain canonical concept:\n"
    "  - Fold the fork's behaviour into the base class/function and migrate callers.\n"
    "  - Use a DESCRIPTIVE name for a genuinely distinct concept (MultiSource, Combined,\n"
    "    Composite, ...), never a synonym (Advanced/Aggregated are also banned).\n"
    "  Suppress with:  # canonical: ignore py-duplicate-concept — <reason> (#NNNN)"
)

# Era-marker tokens that signal canonical drift. Matched case-insensitively as a
# substring so prefix (EnhancedX), infix (XEnhancedY) and standalone all fire.
_BANNED_TOKENS = ("enhanced", "unified", "consolidated")
# Allow-list: substrings whose presence makes an otherwise-matching name legitimate.
# "unified diff" is a git output format, not an era marker.
_ALLOWLIST = ("unified_diff",)
_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-duplicate-concept\b")


def _is_test_file(file_path: Path) -> bool:
    """Migration / back-compat tests legitimately reference the old era-marker names."""
    name = file_path.name
    return name.endswith("_test.py") or name.startswith("test_") or "tests" in file_path.parts


def _banned_token(name: str) -> str | None:
    lowered = name.lower()
    if any(allowed in lowered for allowed in _ALLOWLIST):
        return None
    for token in _BANNED_TOKENS:
        if token in lowered:
            return token
    return None


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    if _is_test_file(file_path):
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    diagnostics: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        token = _banned_token(node.name)
        if token is None:
            continue
        idx = node.lineno - 1
        if 0 <= idx < len(lines) and _WAIVER.search(lines[idx]):
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        diagnostics.append(
            Diagnostic(
                rule_id=RULE_ID,
                issue=ISSUE,
                severity=SEVERITY,
                file=file_path,
                line=node.lineno,
                col=node.col_offset,
                message=f"{kind} '{node.name}' carries era-marker '{token}' — rename to the canonical concept",
                snippet=(lines[idx].strip()[:120] if 0 <= idx < len(lines) else ""),
                fix_hint=FIX_HINT,
            )
        )
    return diagnostics
