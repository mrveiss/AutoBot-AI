# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression guard: knowledge modules must not eagerly import llama_index (#11391).

`knowledge/base.py` and `knowledge/facts.py` used unguarded top-level
`from llama_index...` imports, so any import chain reaching them (e.g.
`workflow_automation -> orchestrator -> knowledge_base`) hard-failed with
ModuleNotFoundError in an environment without the (heavy, optional-in-tests)
llama_index family — which blocked scoped test collection such as
`tests/services/test_concurrent_limiter.py`.

llama_index must only be imported lazily (inside the functions that use it) or
under `if TYPE_CHECKING:`. This test enforces that at the source level so it
cannot silently regress, and also proves the modules import with llama_index
absent.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GUARDED_MODULES = ["knowledge/base.py", "knowledge/facts.py"]


def _module_level_llama_imports(source: str) -> list[str]:
    """Return llama_index imports that sit at module scope and outside TYPE_CHECKING."""
    tree = ast.parse(source)
    offenders: list[str] = []

    def _is_llama(node: ast.AST) -> bool:
        if isinstance(node, ast.ImportFrom):
            return bool(node.module and node.module.startswith("llama_index"))
        if isinstance(node, ast.Import):
            return any(a.name.startswith("llama_index") for a in node.names)
        return False

    for node in tree.body:  # module-level statements only
        if _is_llama(node):
            offenders.append(f"line {node.lineno}: top-level llama_index import")
        # `if TYPE_CHECKING:` blocks are allowed to import llama_index.
        if isinstance(node, ast.If):
            continue  # type-checking / conditional guards are fine
    return offenders


@pytest.mark.parametrize("rel_path", _GUARDED_MODULES)
def test_no_unguarded_top_level_llama_index_import(rel_path: str) -> None:
    source = (_BACKEND_ROOT / rel_path).read_text(encoding="utf-8")
    offenders = _module_level_llama_imports(source)
    assert not offenders, f"{rel_path} must import llama_index lazily / under TYPE_CHECKING, found: {offenders}"


def test_knowledge_base_imports_without_llama_index(monkeypatch) -> None:
    """knowledge.base + knowledge.facts import even when llama_index is absent."""
    saved = {k: v for k, v in sys.modules.items() if k.startswith("llama_index")}
    for k in saved:
        monkeypatch.delitem(sys.modules, k, raising=False)
    # Force any `import llama_index.*` to raise ModuleNotFoundError.
    monkeypatch.setitem(sys.modules, "llama_index", None)
    for mod in ("knowledge.base", "knowledge.facts"):
        monkeypatch.delitem(sys.modules, mod, raising=False)
        importlib.import_module(mod)  # must not raise ModuleNotFoundError
