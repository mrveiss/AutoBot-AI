# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ChromaDB collection name the backend source creates or names (#20945 guard input).

The knowledge-graph guard derives its collection list from this scan, not from a hand-kept tuple, so a
collection added anywhere in the backend fails the guard until a graph section maps it (or it is
explicitly excluded). A name counts when it is: a string assigned to a ``*COLLECTION`` / ``*COLLECTION_NAME``
name; a string in a ``*COLLECTIONS`` tuple; the literal name given to
``get_or_create_collection`` / ``get_collection`` / ``create_collection``; or the default of a
``*collection_name`` config lookup.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterator, Set

_NAME_CONST = re.compile(r"(COLLECTION|COLLECTION_NAME)$", re.IGNORECASE)
_NAME_GROUP = re.compile(r"COLLECTIONS$")
_CREATORS = {"get_or_create_collection", "get_collection", "create_collection"}
# Enum members and other strings named like a collection that are not ChromaDB collections.
NOT_COLLECTIONS = frozenset({"unbounded_collection", "monitoring_collection"})
_SKIP_PARTS = {"tests", "test", "node_modules", "venv", "__pycache__", "archive", "backups"}


def _target_name(target: ast.AST) -> str:
    return target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")


def _strings(node: ast.AST | None) -> Iterator[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        yield node.value
    elif isinstance(node, (ast.Tuple, ast.List)):
        for item in node.elts:
            yield from _strings(item)


def _from_assign(node: ast.Assign | ast.AnnAssign) -> Iterator[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        name = _target_name(target)
        if _NAME_CONST.search(name) or _NAME_GROUP.search(name):
            yield from _strings(node.value)


def _from_call(node: ast.Call) -> Iterator[str]:
    func = getattr(node.func, "attr", "")
    if func in _CREATORS:
        arg = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "name"), None)
        yield from _strings(arg)
    elif func == "get" and len(node.args) == 2 and "collection_name" in "".join(_strings(node.args[0])):
        yield from _strings(node.args[1])


def names_in_source(source: str) -> Set[str]:
    """The collection names one module's source names."""
    found: Set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            found.update(_from_assign(node))
        elif isinstance(node, ast.Call):
            found.update(_from_call(node))
    return {n for n in found if n and "{" not in n} - NOT_COLLECTIONS


def backend_collection_names(root: Path) -> Set[str]:
    """Collection names named anywhere under *root* (test files and vendored trees skipped)."""
    names: Set[str] = set()
    for path in sorted(root.rglob("*.py")):
        if _SKIP_PARTS & set(path.relative_to(root).parts) or path.stem.startswith("test_") or "_test" in path.stem:
            continue
        try:
            names |= names_in_source(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
    return names
