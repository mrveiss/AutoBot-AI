# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: one chat-session delete implementation (#18316).

`DELETE /chats/{chat_id}` called the async `delete_session` without `await` and
reported success while deleting nothing. The root cause was a second delete path
beside the canonical `DELETE /chat/sessions/{session_id}`, so only the canonical
module (`api/chat_sessions.py`) may call `delete_session(` on the chat history
manager; every other route delegates to it.

Scope: a call whose receiver name contains `chat_history`. The verbatim-memory
store has its own unrelated `delete_session` and is not matched.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_API = repo_root() / "autobot-backend" / "api"
_CANONICAL = "chat_sessions.py"
_MIN_FILES_SCANNED = 100


def _receiver_name(node: ast.Attribute) -> str:
    value = node.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return ""


def _direct_delete_calls(source: str) -> list[int]:
    """Line numbers of `<...chat_history...>.delete_session(` calls."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        func = getattr(node, "func", None)
        if isinstance(node, ast.Call) and isinstance(func, ast.Attribute):
            if func.attr == "delete_session" and "chat_history" in _receiver_name(func):
                lines.append(node.lineno)
    return lines


def _scan() -> tuple[int, dict[str, list[int]]]:
    scanned, offenders = 0, {}
    for path in sorted(_API.rglob("*.py")):
        if path.name.endswith("_test.py") or path.name == _CANONICAL:
            continue
        scanned += 1
        found = _direct_delete_calls(path.read_text(encoding="utf-8"))
        if found:
            offenders[str(path.relative_to(_API))] = found
    return scanned, offenders


def test_only_the_canonical_route_deletes_a_chat_session() -> None:
    scanned, offenders = _scan()
    assert scanned >= _MIN_FILES_SCANNED, f"scanned only {scanned} files; the sweep did not look"
    assert not offenders, (
        f"direct chat_history_manager.delete_session( outside {_CANONICAL}: {offenders}. "
        "Delegate to the canonical delete route logic instead (#18316)."
    )


def test_the_canonical_module_does_delete_so_the_scan_can_see_one() -> None:
    source = (_API / _CANONICAL).read_text(encoding="utf-8")
    assert _direct_delete_calls(source), "canonical delete call not found: matcher is blind"


def test_contrast_a_second_route_calling_delete_session_is_caught() -> None:
    bad = (
        "async def route(request):\n"
        "    chat_history_manager = get(request)\n"
        "    return chat_history_manager.delete_session(session_id='x')\n"
    )
    good = "async def route(request):\n    return await store.delete_session('x')\n"
    assert _direct_delete_calls(bad) == [3]
    assert _direct_delete_calls(good) == []
