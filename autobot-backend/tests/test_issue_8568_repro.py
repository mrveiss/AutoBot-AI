# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for GH#8568 — dead import LLCWorkItem in llc/kb/inheritance.py.

PR #8554 introduced `from ..models.work_item import LLCWorkItem` at line 19 of
inheritance.py, but LLCWorkItem is never referenced anywhere in the file.
The flake8 F401 pre-commit hook (enforced since #6973) rejects any commit
that touches the file while this import is present.

This test FAILS on the unfixed code and PASSES once line 19 is removed.
"""

from __future__ import annotations

import ast
from pathlib import Path


def test_inheritance_has_no_dead_llcworkitem_import() -> None:
    """inheritance.py must not import LLCWorkItem — it is never referenced (GH#8568)."""
    source_path = Path(__file__).resolve().parent.parent / "llc" / "kb" / "inheritance.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))

    # Collect every name brought into scope by an `import` or `from … import` statement.
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.append(alias.asname if alias.asname else alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.append(alias.asname if alias.asname else alias.name)

    assert "LLCWorkItem" not in imported, (
        "Dead import detected in llc/kb/inheritance.py: "
        "'from ..models.work_item import LLCWorkItem' is present but LLCWorkItem "
        "is never used in the file. Remove the import to fix the flake8 F401 "
        "pre-commit failure introduced by PR #8554 (GH#8568)."
    )
