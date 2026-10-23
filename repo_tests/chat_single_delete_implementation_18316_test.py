# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: one chat-session delete implementation (#18316, #18293).

`DELETE /chats/{chat_id}` called the async `delete_session` without `await` and
reported success while deleting nothing. The root cause was a second delete path
beside the canonical `DELETE /chat/sessions/{session_id}`. Since #18293 the one
place that calls `delete_session(` on the chat history manager is
`api/legacy_transcript_disposal.delete_session_or_refer` -- it deletes the session
first and refers a legacy-only transcript to #17038 review -- and every route
(both `DELETE /chat/sessions/{id}` and `DELETE /chats/{id}`) delegates to it.

Scope: a call whose receiver name contains `chat_history`, in non-test python under
`autobot-backend/api`. The verbatim-memory store has its own unrelated
`delete_session` and is not matched.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend/api",)
_CANONICAL = "autobot-backend/api/legacy_transcript_disposal.py"
_CANONICAL_FUNCTION = "delete_session_or_refer"


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _api_sources(root: Path) -> list[str]:
    try:
        return [rel for rel in tracked_paths(root, *_ROOTS) if _is_source_python(rel)]
    except EmptyEnumeration:
        return []


#: Mid-window from REACH.window(): 433 non-test api modules measured 2026-10-13 (train-9c), window [393, 433].
REACH = declare(
    "chat-single-delete-implementation",
    discover=_api_sources,
    floor=430,  # re-pinned mid-window (train 45): population 450, window [410, 450]
    growth=40,
    what="non-test python modules",
    roots=_ROOTS,
)


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


def _delete_functions(source: str) -> list[str]:
    """Names of the functions that contain a direct chat-history delete call."""
    return [
        fn.name
        for fn in ast.walk(ast.parse(source))
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and _direct_delete_calls(ast.unparse(fn))
    ]


def _offenders() -> dict[str, list[int]]:
    root = repo_root()
    offenders = {}
    for rel in REACH.examined(root):
        if rel == _CANONICAL:
            continue
        found = _direct_delete_calls((root / rel).read_text(encoding="utf-8"))
        if found:
            offenders[rel] = found
    return offenders


def test_only_the_canonical_function_deletes_a_chat_session() -> None:
    offenders = _offenders()
    assert not offenders, (
        f"direct chat_history_manager.delete_session( outside {_CANONICAL}: {offenders}. "
        f"Delegate to {_CANONICAL_FUNCTION} instead (#18316, #18293)."
    )


def test_the_canonical_module_does_delete_so_the_scan_can_see_one() -> None:
    source = (repo_root() / _CANONICAL).read_text(encoding="utf-8")
    assert _delete_functions(source) == [_CANONICAL_FUNCTION], "canonical delete call not found: matcher is blind"


def test_contrast_a_second_route_calling_delete_session_is_caught() -> None:
    bad = (
        "async def route(request):\n"
        "    chat_history_manager = get(request)\n"
        "    return chat_history_manager.delete_session(session_id='x')\n"
    )
    good = "async def route(request):\n    return await store.delete_session('x')\n"
    assert _direct_delete_calls(bad) == [3]
    assert _direct_delete_calls(good) == []
