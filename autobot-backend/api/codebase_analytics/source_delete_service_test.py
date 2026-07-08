# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""delete_source_and_cleanup removes clone dir + index + record (#11129 P2)."""
import ast
from pathlib import Path

_SVC = Path(__file__).parent / "source_service.py"
_SOURCES = Path(__file__).parent / "endpoints" / "sources.py"


def test_service_exposes_delete_and_cleanup():
    tree = ast.parse(_SVC.read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
    assert "delete_source_and_cleanup" in names


def test_delete_handler_delegates_to_service():
    src = _SOURCES.read_text(encoding="utf-8")
    assert "delete_source_and_cleanup" in src, "DELETE handler must call the extracted service"
