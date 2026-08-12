# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for Issue #13218 — approval status was never recorded because
``approval_handler`` called ``add_message(role=..., metadata=...)`` while
``MessagesMixin.add_message`` is keyword-only and takes ``sender=`` /
``raw_data=``.

The resulting ``TypeError`` was caught and logged as "non-fatal", so every
approve/deny decision silently failed to reach chat history.

Three sibling call sites had the same defect (``metadata=`` instead of
``raw_data=``): ``api/overseer_handlers.py`` (twice) and
``services/agent_terminal/command_executor.py``.

Rather than restating the signature in a stub — which would only test a copy of
it — these tests bind the *real* keyword arguments used at every
``add_message`` call site in the tree against the *real* signature. Before the
fix ``test_every_add_message_call_site_binds`` reports four unbindable call
sites; ``test_persisted_message_carries_sender_and_metadata`` proves the
keywords land in the fields the frontend reads.
"""

import ast
import asyncio
import functools
import inspect
import pathlib
from typing import Any, Dict, List

import pytest

from chat_history.messages import MessagesMixin

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Receiver expressions that denote a ChatHistoryManager. ``add_message`` is also
# the name of an unrelated GatewaySession method in services/gateway, so the scan
# is scoped by receiver rather than by method name alone.
CHAT_HISTORY_RECEIVERS = ("chat_mgr", "chat_history", "chat_history_manager")


class _RecordingHistory(MessagesMixin):
    """Exercises the real ``add_message`` against an in-memory session store."""

    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}

    async def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self.sessions.get(session_id, []))

    async def save_session(self, session_id: str, messages: List[Dict[str, Any]], **_: Any) -> bool:
        self.sessions[session_id] = list(messages)
        return True


@functools.lru_cache(maxsize=1)
def _add_message_call_sites() -> List[tuple]:
    """Collect (path, lineno, positional_count, keywords) for every add_message call."""
    call_sites = []
    for path in BACKEND_ROOT.rglob("*.py"):
        if path.name.endswith("_test.py"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - unparseable file is a different failure
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "add_message":
                continue
            receiver = ast.unparse(node.func.value).split(".")[-1]
            if receiver not in CHAT_HISTORY_RECEIVERS:
                continue
            # A **splat or *args site cannot be bound statically: kw.arg is None for
            # **kwargs, and a Starred node is not one positional. Binding them anyway
            # fails on correct code, so they are skipped rather than mis-scanned.
            if any(kw.arg is None for kw in node.keywords) or any(isinstance(a, ast.Starred) for a in node.args):
                continue
            keywords = [kw.arg for kw in node.keywords]
            call_sites.append((path, node.lineno, len(node.args), keywords))
    return call_sites


def test_add_message_call_sites_are_discoverable() -> None:
    """Guard the scan itself: if it finds nothing, the binding test is vacuous."""
    sites = _add_message_call_sites()
    # Floor, not an exact count: the scan is receiver-scoped, so a rename of
    # chat_history_manager could erode 18 -> 1 and still be "non-empty".
    assert len(sites) >= 15, f"expected >=15 add_message call sites, found {len(sites)} — scan is eroding"


def test_every_add_message_call_site_binds() -> None:
    """Every add_message call site matches the real keyword-only signature."""
    signature = inspect.signature(MessagesMixin.add_message)
    failures = []

    for path, lineno, positional_count, keywords in _add_message_call_sites():
        try:
            signature.bind(
                None,
                *([None] * positional_count),
                **{kw: None for kw in keywords},
            )
        except TypeError as exc:
            failures.append(f"{path.relative_to(BACKEND_ROOT)}:{lineno} -> {exc}")

    assert not failures, "add_message called with arguments the signature rejects:\n" + "\n".join(failures)


def test_persisted_message_carries_sender_and_metadata() -> None:
    """sender= and raw_data= land in the 'sender' and 'metadata' message fields."""
    manager = _RecordingHistory()
    approval_metadata = {"approval_status": "approved", "command": "ls -la"}

    asyncio.run(
        manager.add_message(
            session_id="session-13218",
            sender="system",
            text="Command approved and executed: `ls -la`",
            message_type="command_approval_response",
            raw_data=approval_metadata,
        )
    )

    stored = manager.sessions["session-13218"]
    assert len(stored) == 1
    assert stored[0]["sender"] == "system"
    assert stored[0]["messageType"] == "command_approval_response"
    assert stored[0]["metadata"] == approval_metadata


def test_role_keyword_is_rejected() -> None:
    """'role' is not — and must not silently become — an accepted keyword."""
    manager = _RecordingHistory()

    with pytest.raises(TypeError):
        asyncio.run(manager.add_message(role="system", text="x"))  # type: ignore[call-arg]
