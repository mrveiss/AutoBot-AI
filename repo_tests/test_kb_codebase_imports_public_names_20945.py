# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The knowledge graph's codebase nodes import only public names from codebase_analytics (#20945).

A ``_``-prefixed name is private to its home module; a cross-package import of one silently pins the
other package's internals. The home module exports a public name instead.
"""

import ast

from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache

TARGET = repo_root() / "autobot-backend" / "api" / "knowledge_graph_codebase.py"
PACKAGE = "api.codebase_analytics"


def private_imports(source: str) -> list[str]:
    """``module.name`` for every ``_``-prefixed name imported from the codebase_analytics package."""
    found = []
    for node in ast.walk(parse_cache.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(PACKAGE):
            found += [f"{node.module}.{a.name}" for a in node.names if a.name.startswith("_")]
    return found


def test_the_codebase_nodes_import_no_private_name_from_codebase_analytics():
    assert private_imports(TARGET.read_text(encoding="utf-8")) == []


def test_the_guard_catches_a_planted_private_import():
    planted = "from api.codebase_analytics.endpoints.shared import _caller_owner_id, resolve_scan_root\n"
    assert private_imports(planted) == ["api.codebase_analytics.endpoints.shared._caller_owner_id"]
