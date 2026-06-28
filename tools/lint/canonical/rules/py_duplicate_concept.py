# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-duplicate-concept — flag Enhanced*/Unified* class names that shadow a base.

An ``EnhancedFoo`` next to ``Foo`` (or ``UnifiedFoo`` next to ``Foo``) is a
canonical-debt signal: instead of extending the original in place, a prefixed
fork was created. The prefixed classes should be renamed or merged into the
canonical module. WARN severity — 30+ existing instances must be migrated
before this can be promoted to BLOCK. See canonical-debt umbrella #10569.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-duplicate-concept"
ISSUE = "#10577"
SEVERITY = "warn"
TARGETS = ["autobot-backend", "autobot-slm-backend", "autobot_shared"]
DESCRIPTION = "Enhanced*/Unified* class shadows a base concept — merge into the canonical class"
FIX_HINT = (
    "Rename or fold EnhancedX/UnifiedX into the canonical X class:\n"
    "  - If the prefix adds behaviour, extend the canonical class via inheritance.\n"
    "  - If they have diverged, consolidate and delete the prefixed fork.\n"
    "  Suppress with:  # canonical: ignore py-duplicate-concept — <reason> (#NNNN)"
)

_PREFIXES = ("Enhanced", "Unified")
_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-duplicate-concept\b")


def _class_names(tree: ast.AST) -> set[str]:
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    all_names = _class_names(tree)
    diagnostics: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_name = _strip_prefix(node.name)
        if base_name is None or base_name not in all_names:
            continue
        idx = node.lineno - 1
        if 0 <= idx < len(lines) and _WAIVER.search(lines[idx]):
            continue
        diagnostics.append(
            Diagnostic(
                rule_id=RULE_ID,
                issue=ISSUE,
                severity=SEVERITY,
                file=file_path,
                line=node.lineno,
                col=node.col_offset,
                message=f"'{node.name}' shadows base concept '{base_name}' — merge into the canonical class",
                snippet=(lines[idx].strip()[:120] if 0 <= idx < len(lines) else ""),
                fix_hint=FIX_HINT,
            )
        )
    return diagnostics


def _strip_prefix(name: str) -> str | None:
    for prefix in _PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix):
            return name[len(prefix):]
    return None
