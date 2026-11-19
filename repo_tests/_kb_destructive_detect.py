# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The detectors behind ``kb_destructive_paths_guard_21383_test.py`` (#21383, #17038).

Three ways a source file deletes knowledge-base data, each reported as one kind:

* ``index-or-flush``: the text names ``FT.DROPINDEX``, ``dropindex``, ``flushdb`` or ``flushall`` (a regex, so it
  reads ``.sh`` files too);
* ``collection-delete``: Python that names ``delete_collection`` or ``bulk_delete_collection_facts`` as an
  attribute, called or handed on (``asyncio.to_thread(client.delete_collection, ...)``); a definition is not a use;
* ``key-delete``: Python that opens the knowledge database (``"knowledge"`` as the database argument or
  ``RedisDatabase.KNOWLEDGE``) and also unlinks keys or deletes them in bulk (``delete(*keys)``).
"""

from __future__ import annotations

import ast
import re

from tools.lint._parse_cache import parse

INDEX_OR_FLUSH = "index-or-flush"
COLLECTION_DELETE = "collection-delete"
KEY_DELETE = "key-delete"

_INDEX_OR_FLUSH_RE = re.compile(r"dropindex|flushdb|flushall", re.IGNORECASE)
_COLLECTION_VERBS = frozenset({"delete_collection", "bulk_delete_collection_facts"})
_DATABASE_KEYWORDS = frozenset({"database", "db", "redis_db"})


def _is_knowledge_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "knowledge"


def _names_database_constant(node: ast.AST) -> bool:
    """``DATABASE = "knowledge"``: a module constant a client factory is later called with."""
    if not (isinstance(node, ast.Assign) and _is_knowledge_name(node.value)):
        return False
    return any(isinstance(t, ast.Name) and ("DATABASE" in t.id or t.id.endswith("_DB")) for t in node.targets)


def _opens_knowledge_db(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "KNOWLEDGE":
        return True
    if _names_database_constant(node):
        return True
    if isinstance(node, ast.keyword):
        return node.arg in _DATABASE_KEYWORDS and _is_knowledge_name(node.value)
    return isinstance(node, ast.Call) and bool(node.args) and _is_knowledge_name(node.args[0])


def _is_os_module(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id in ("os", "_os")


def _deletes_keys(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return False
    if node.func.attr == "unlink":  # a Redis UNLINK, not ``Path.unlink`` / ``os.unlink`` on a file
        return not any(k.arg == "missing_ok" for k in node.keywords) and not _is_os_module(node.func.value)
    return node.func.attr == "delete" and any(isinstance(a, ast.Starred) for a in node.args)


def _python_kinds(source: str, filename: str) -> set[str]:
    tree = parse(source, filename)
    nodes = list(ast.walk(tree))
    kinds = set()
    if any(isinstance(n, ast.Attribute) and n.attr in _COLLECTION_VERBS for n in nodes):
        kinds.add(COLLECTION_DELETE)
    if any(_opens_knowledge_db(n) for n in nodes) and any(_deletes_keys(n) for n in nodes):
        kinds.add(KEY_DELETE)
    return kinds


def kinds_in(source: str, filename: str) -> set[str]:
    """Which destructive kinds *source* contains; an unparseable ``.py`` yields only the text match."""
    kinds = {INDEX_OR_FLUSH} if _INDEX_OR_FLUSH_RE.search(source) else set()
    if filename.endswith(".py"):
        try:
            kinds |= _python_kinds(source, filename)
        except SyntaxError:
            pass
    return kinds
