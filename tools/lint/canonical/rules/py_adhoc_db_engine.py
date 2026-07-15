# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-adhoc-db-engine — flag ad-hoc SQLAlchemy engine/session construction.

Production code must obtain sessions from the canonical async session factory
(``user_management/database.py``), not build its own ``create_engine`` +
``sessionmaker``. Ad-hoc construction bypasses pool tuning, health checks, and
the async-first contract. Migration code and the canonical factory itself are
exempt. See canonical-debt umbrella #10569.

Promoted to BLOCK in #10627 (py-adhoc-db-engine cohort): all 39 pre-existing
call sites have been either migrated to the canonical factory or waived with
``# canonical: ignore py-adhoc-db-engine`` where the sync wrapper over the
canonical engine (background threads / DataLoader workers) or a test-local
in-memory engine is genuinely required.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-adhoc-db-engine"
ISSUE = "#10570"
SEVERITY = "block"
TARGETS = ["autobot-backend", "autobot-slm-backend"]
DESCRIPTION = "Ad-hoc create_engine/sessionmaker — use the canonical async session factory"
FIX_HINT = (
    "Obtain sessions from the canonical factory instead of building your own:\n"
    "    from user_management.database import get_async_session_factory\n"
    "    Session = get_async_session_factory()"
)

_BANNED = frozenset({"create_engine", "create_async_engine", "sessionmaker", "async_sessionmaker"})
_EXEMPT_NAMES = frozenset({"database.py", "db.py", "base.py"})
_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-adhoc-db-engine\b")


def _is_exempt(file_path: Path) -> bool:
    parts = file_path.parts
    return "migrations" in parts or "alembic" in parts or file_path.name in _EXEMPT_NAMES


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    if _is_exempt(file_path):
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    diagnostics: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
        if name not in _BANNED:
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
                message=f"ad-hoc {name}() — use the canonical async session factory",
                snippet=(lines[idx].strip()[:120] if 0 <= idx < len(lines) else ""),
                fix_hint=FIX_HINT,
            )
        )
    return diagnostics
