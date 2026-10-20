# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18954 — ``autobot_shared.paths`` stays stdlib-only.

The bare lint hooks and the file-size guards import it under a hook interpreter
with no third-party packages; one non-stdlib import there turns every commit's
hook into a ModuleNotFoundError. Checked by AST over the import statements, so a
docstring or comment mentioning a package cannot trip or mask it.
"""

from __future__ import annotations

import ast
import sys

from repo_tests._paths import repo_root

_PATHS = repo_root() / "autobot_shared" / "paths.py"


def _imported_top_levels(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_paths_imports_only_the_standard_library():
    tree = ast.parse(_PATHS.read_text(encoding="utf-8"))
    foreign = sorted(_imported_top_levels(tree) - set(sys.stdlib_module_names) - {"__future__"})
    assert foreign == [], f"autobot_shared/paths.py imports non-stdlib modules: {foreign}"


def test_the_stdlib_scan_flags_a_third_party_import():
    """Contrast: the same scan over a synthetic module that imports yaml reports it."""
    tree = ast.parse("import os\nfrom yaml import safe_load\n")
    assert _imported_top_levels(tree) - set(sys.stdlib_module_names) == {"yaml"}
