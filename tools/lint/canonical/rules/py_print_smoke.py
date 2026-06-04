"""py-print-smoke — pipeline smoke-test rule.

Detects bare `print()` calls in production Python code. Aliases the existing
no-print-console pre-commit hook but routes through the canonical-check
registry — exists only to prove the pipeline. WARN severity so it never blocks.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-print-smoke"
ISSUE = "#7458"
SEVERITY = "warn"
TARGETS = ["autobot-backend", "autobot-slm-backend", "autobot_shared", "tests/lint/canonical/fixtures"]
DESCRIPTION = "print() in production code — pipeline smoke-test rule for canonical-check"
FIX_HINT = (
    "Replace print() with a logger call:\n"
    "    from autobot_shared.logging import get_logger\n"
    "    logger = get_logger(__name__)\n"
    '    logger.info("...")'
)

_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-print-smoke\b")


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    try:
        source_lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    diagnostics: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"):
            continue
        line_idx = node.lineno - 1
        if 0 <= line_idx < len(source_lines) and _WAIVER.search(source_lines[line_idx]):
            continue
        snippet = source_lines[line_idx].strip() if 0 <= line_idx < len(source_lines) else ""
        diagnostics.append(
            Diagnostic(
                rule_id=RULE_ID,
                issue=ISSUE,
                severity=SEVERITY,
                file=file_path,
                line=node.lineno,
                col=node.col_offset,
                message="print() in production code — use logger",
                snippet=snippet[:120],
                fix_hint=FIX_HINT,
            )
        )
    return diagnostics
