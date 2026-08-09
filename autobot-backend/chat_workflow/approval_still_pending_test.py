# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A turn that stops waiting must not call a live approval a failed command (#13481).

`_handle_approval_failure` reported two different outcomes identically, as
``type="error"``:

* the user **denied** the command — a real, final failure;
* the turn's poll budget ran out with **no decision** — not a failure at all.

The second case emitted ``Approval timeout for command: ls -la``, which says the
command failed. It had neither failed nor run, and the user could still make it
run. Verified against the code rather than assumed:

* the poll timing out does not clear the pending approval —
  ``clear_pending_and_resume()`` is called only on the approve/deny paths
  (``services/agent_terminal/service.py:456,602``);
* ``AgentTerminalService._approve_command_internal`` executes the command on
  approve with no coroutine waiting, then broadcasts over ``events.bus``.

So approving afterwards still runs it. The message was the bug, and it is what
made #13216 read as "approving afterwards does not run it".
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


def _handler():
    """The handler under test, constructed without its heavy collaborators.

    ``_handle_approval_failure`` is a pure function of its two arguments — it
    touches no instance state — so a bare subclass instance avoids dragging in
    the terminal service, Ollama client and chat-history manager that the real
    composing class builds in ``__init__``.
    """
    from chat_workflow.tool_handler import ToolHandlerMixin

    class _Handler(ToolHandlerMixin):
        pass

    return _Handler()


async def test_a_denial_is_still_reported_as_a_failure():
    """The real failure case must not get softened by this change."""
    msg, text = _handler()._handle_approval_failure("rm -rf /tmp/x", {"error": "denied by user"})

    assert msg.type == "error"
    assert msg.metadata["error"] is True
    assert "denied by user" in msg.content
    assert "❌" in text


async def test_no_decision_is_not_reported_as_an_error():
    """The regression: a pending approval rendered as a failed command."""
    msg, text = _handler()._handle_approval_failure("ls -la", None)

    assert msg.type != "error", (
        "a turn giving up on waiting is not a command failure — the approval is "
        "still pending and approving it still executes the command"
    )
    assert "failed" not in msg.content.lower()
    assert "❌" not in text


async def test_no_decision_says_the_approval_is_still_actionable():
    """The user has to be able to tell that approving still does something."""
    msg, text = _handler()._handle_approval_failure("ls -la", None)

    assert "ls -la" in msg.content
    assert "approving it will run the command" in msg.content.lower()
    assert msg.metadata["approval_still_actionable"] is True
    assert msg.metadata["message_type"] == "approval_still_pending"
    assert "still waiting" in text.lower()


async def test_the_legacy_timeout_flag_is_preserved():
    """Consumers keying on ``metadata['timeout']`` must not break.

    Its meaning narrows — "this turn stopped waiting", not "the approval
    expired" — but dropping it would silently change behaviour for anything
    already branching on it.
    """
    msg, _ = _handler()._handle_approval_failure("ls -la", None)
    assert msg.metadata["timeout"] is True


async def test_no_approval_expiry_knob_exists():
    """The wait budget bounds the turn, never the approval's life (#13216).

    An expiry knob here would re-create the defect: an approval discarded as a
    side effect of how long a coroutine lived. If a real expiry policy is ever
    wanted it belongs with the approval's storage, with its own message.
    """
    import chat_workflow.tool_handler as mod

    expiry_names = [
        name for name in dir(mod) if "APPROVAL" in name and ("EXPIR" in name or "TTL" in name or "MAX_AGE" in name)
    ]
    assert not expiry_names, (
        f"an approval-expiry knob appeared in tool_handler: {expiry_names} — "
        "the turn's wait budget must not double as the approval's lifetime"
    )
