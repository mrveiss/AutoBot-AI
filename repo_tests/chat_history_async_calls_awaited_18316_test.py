# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: every async ``ChatHistoryManager`` call in the API is consumed (#18316 AC3).

``DELETE /chats/{chat_id}`` called ``chat_history_manager.delete_session(...)`` without
``await``: the coroutine was created, never run, and the route answered 200 while the
session survived. This sweeps ``autobot-backend/api`` for the whole class, not that one
call.

* The method set is DERIVED from the class: every ``async def`` that
  ``ChatHistoryManager`` exposes through its MRO, so a new async method is covered the
  day it lands.
* A receiver is a chat-history manager when its text names one (``chat_history``,
  ``chat_mgr``, ``ChatHistoryManager``), or it is a local name assigned from an
  expression that does (``m = get_chat_history_manager(request)``).
* A call is consumed when it is awaited, returned, or handed to ``create_task``,
  ``gather``, ``ensure_future``, ``wait_for`` or ``shield``.

What it cannot see, stated so "0 found" is read correctly: a manager reached through a
name that mentions none of those tokens and is bound somewhere other than a plain
assignment in the same module (a parameter called ``store``, an attribute set in
``__init__`` under another name). Measured 2026-10-11: 39 recognised calls in the
population, all consumed -- 0 un-awaited calls found besides the one #18316 fixed, which
this detector flags on the pre-fix ``api/chat.py`` (contrast below).
"""

from __future__ import annotations

import ast
import functools
import inspect
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend/api",)
_MANAGER_TOKEN = re.compile(r"chat_history|chat_mgr|ChatHistoryManager")
_CONSUMERS = frozenset({"create_task", "gather", "ensure_future", "wait_for", "shield"})


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _api_sources(root: Path) -> list[str]:
    try:
        return [rel for rel in tracked_paths(root, *_ROOTS) if _is_source_python(rel)]
    except EmptyEnumeration:
        return []


#: Mid-window from REACH.window(): 416 non-test api modules measured 2026-10-11, window [376, 416].
REACH = declare(
    "chat-history-async-calls-awaited",
    discover=_api_sources,
    floor=430,  # re-pinned mid-window (train 45): population 450, window [410, 450]
    growth=40,
    what="non-test python modules",
    roots=_ROOTS,
)


@functools.lru_cache(maxsize=1)
def async_methods() -> frozenset[str]:
    """Every ``async def`` the real ``ChatHistoryManager`` exposes, mixins included."""
    from chat_history import ChatHistoryManager

    return frozenset(name for name, fn in inspect.getmembers(ChatHistoryManager) if inspect.iscoroutinefunction(fn))


def _bound_managers(tree: ast.AST) -> set[str]:
    """Local names assigned from an expression that names a chat-history manager."""
    return {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and _MANAGER_TOKEN.search(ast.unparse(node.value))
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _consumed(call: ast.Call, parent: ast.AST | None) -> bool:
    if isinstance(parent, (ast.Await, ast.Return)):
        return True
    return isinstance(parent, ast.Call) and ast.unparse(parent.func).rsplit(".", 1)[-1] in _CONSUMERS


def unawaited_calls(source: str, methods: frozenset[str]) -> list[str]:
    """``line:receiver.method`` for every chat-history async call that is not consumed."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    bound = _bound_managers(tree)
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in methods):
            continue
        receiver = node.func.value
        is_manager = _MANAGER_TOKEN.search(ast.unparse(receiver)) or (
            isinstance(receiver, ast.Name) and receiver.id in bound
        )
        if is_manager and not _consumed(node, parents.get(node)):
            found.append(f"{node.lineno}:{ast.unparse(receiver)}.{node.func.attr}")
    return found


_M = frozenset({"delete_session", "load_session"})


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        (
            "the #18316 bug",
            "async def r(chat_history_manager):\n    chat_history_manager.delete_session('x')\n",
            ["2:chat_history_manager.delete_session"],
        ),
        (
            "bound by assignment",
            "async def r(q):\n    m = get_chat_history_manager(q)\n    m.load_session('x')\n",
            ["3:m.load_session"],
        ),
        ("awaited", "async def r(chat_history_manager):\n    await chat_history_manager.delete_session('x')\n", []),
        ("returned", "def r(chat_mgr):\n    return chat_mgr.load_session('x')\n", []),
        ("handed to gather", "async def r(chat_mgr):\n    await asyncio.gather(chat_mgr.load_session('x'))\n", []),
        ("another store's delete_session", "async def r(store):\n    store.delete_session('x')\n", []),
        ("a sync method name", "async def r(chat_mgr):\n    chat_mgr.get_all_messages()\n", []),
    ],
)
def test_the_detector_tells_a_lost_coroutine_from_a_consumed_one(label: str, source: str, expected: list[str]) -> None:
    assert unawaited_calls(source, _M) == expected, label


def test_the_method_set_is_derived_from_the_class() -> None:
    methods = async_methods()
    assert {"delete_session", "load_session", "save_session", "add_message"} <= methods
    assert "get_all_messages" not in methods  # sync on the class, so never flagged


def test_no_api_module_drops_a_chat_history_coroutine() -> None:
    root = repo_root()
    methods = async_methods()
    offenders = {
        rel: hits
        for rel in REACH.examined(root)
        if (hits := unawaited_calls((root / rel).read_text(encoding="utf-8"), methods))
    }
    assert not offenders, (
        f"#18316: un-awaited async ChatHistoryManager calls (the coroutine never runs): {offenders}. "
        "Await it, return it, or hand it to create_task/gather."
    )
