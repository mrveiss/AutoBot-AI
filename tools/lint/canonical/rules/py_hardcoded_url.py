# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""py-hardcoded-url — flag hardcoded localhost/loopback URLs with a port.

Hosts and ports belong in ``autobot_shared.ssot_config``, not inline string
literals. Docstrings are ignored (documentation may cite example URLs); only
real string values are flagged. See canonical-debt umbrella #10569.

Production-scope (test fixtures use mock URLs); BLOCK after #10627/#10641 cleaned all prod sites.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.lint.canonical.context import Context
from tools.lint.canonical.diagnostic import Diagnostic

RULE_ID = "py-hardcoded-url"
ISSUE = "#10573"
SEVERITY = "block"
TARGETS = ["autobot-backend", "autobot-slm-backend"]
DESCRIPTION = "Hardcoded localhost/127.0.0.1:port literal — resolve via ssot_config"
FIX_HINT = (
    "Resolve hosts/ports through the SSOT config instead of inline literals:\n"
    "    from autobot_shared.ssot_config import config\n"
    "    url = config.get_service_url(...)"
)

_PATTERN = re.compile(r"https?://(?:localhost|127\.0\.0\.1):\d+")
_WAIVER = re.compile(r"#\s*canonical:\s*ignore\s+py-hardcoded-url\b")


def _docstring_constant_ids(tree: ast.AST) -> set[int]:
    """ids of Constant nodes that are bare-expression strings (docstrings)."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            out.add(id(node.value))
    return out


def _is_test_file(file_path: Path) -> bool:
    """Test fixtures legitimately use mock localhost URLs (not SSOT-resolvable)."""
    name = file_path.name
    return name.endswith("_test.py") or name.startswith("test_") or "tests" in file_path.parts


def check(file_path: Path, tree: ast.AST, ctx: Context) -> list[Diagnostic]:
    # Production-scope rule: SSOT config is for prod hosts/ports. Test files use
    # mock localhost URLs that cannot resolve through ssot_config (#10569 AC).
    if _is_test_file(file_path):
        return []
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    docstrings = _docstring_constant_ids(tree)
    diagnostics: list[Diagnostic] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in docstrings or not _PATTERN.search(node.value):
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
                message="hardcoded localhost/port literal — resolve via ssot_config",
                snippet=(lines[idx].strip()[:120] if 0 <= idx < len(lines) else ""),
                fix_hint=FIX_HINT,
            )
        )
    return diagnostics
