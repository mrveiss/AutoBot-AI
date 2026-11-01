# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Chroma adapter row of #18557: one home for the arguments both adapters send."""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

ADAPTERS = (
    "autobot-backend/knowledge/backends/chromadb_adapter.py",
    "autobot-backend/knowledge/backends/async_chromadb_adapter.py",
)
ARGUMENTS = {"ids", "documents", "metadatas", "embeddings", "include", "query_texts", "query_embeddings"}
OLD_COPY = "def add(self, ids):\n    self._raw.add(ids=list(ids))\n"
OLD_PROVENANCE = "provenance = {'created_at': utc_timestamp()}\n"
DELEGATE = "def add(self, ids):\n    self._raw.add(**write_args(ids, None, None, None))\n"


def own_argument_work(source: str) -> set[str]:
    """Arguments *source* reshapes itself, and the provenance timestamp if it stamps one."""
    found = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "utc_timestamp":
                found.add("provenance")
            if node.func.id == "list" and node.args and isinstance(node.args[0], ast.Name):
                found |= {node.args[0].id} & ARGUMENTS
    return found


def test_the_detector_flags_old_copies_and_passes_a_delegate() -> None:
    assert own_argument_work(OLD_COPY) == {"ids"}
    assert own_argument_work(OLD_PROVENANCE) == {"provenance"}
    assert own_argument_work(DELEGATE) == set()


def test_the_adapters_use_the_shared_arguments() -> None:
    for rel in ADAPTERS:
        source = (repo_root() / rel).read_text(encoding="utf-8")
        assert own_argument_work(source) == set(), rel
        assert "knowledge.backends._chroma_args" in source, rel
