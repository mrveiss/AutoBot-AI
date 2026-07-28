# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Session-id continuity for the Claude Code adapters (Issue #12848).

The adapters generated a uuid4, stored it for later ``--resume``, and never told
the CLI about it — so the CLI minted its own id and every resume failed with
"No conversation found with session ID". Resume had never worked on any run;
agents silently started a fresh conversation on every heartbeat.

The fix claims the id up front with ``--session-id``. Verified against Claude
Code 2.1.220: the CLI adopts the passed id verbatim, and ``--resume`` with that
id replays the conversation. These tests pin the argv contract so the behaviour
cannot revert to always-fresh unnoticed.
"""

import pytest

from llc.adapters.claude_code_adapter import ClaudeCodeAdapter
from llc.adapters.claude_code_subscription_adapter import ClaudeCodeSubscriptionAdapter

_ADAPTERS = [ClaudeCodeAdapter, ClaudeCodeSubscriptionAdapter]


def _fresh(adapter, session_id: str) -> list[str]:
    return adapter._build_command("claude", None, {}, "prompt", session_id=session_id)


def _resume(adapter, session_id: str) -> list[str]:
    return adapter._build_command("claude", session_id, {}, "prompt", session_id=session_id)


def _flag_value(cmd: list[str], flag: str) -> str | None:
    return cmd[cmd.index(flag) + 1] if flag in cmd else None


@pytest.mark.parametrize("adapter", _ADAPTERS)
def test_fresh_run_claims_the_id_we_will_store(adapter):
    """The defect: a fresh run let the CLI pick an id we would never learn."""
    cmd = _fresh(adapter, "sid-1")

    assert _flag_value(cmd, "--session-id") == "sid-1"
    assert "--resume" not in cmd, "a fresh run must not resume"


@pytest.mark.parametrize("adapter", _ADAPTERS)
def test_resume_passes_the_stored_id(adapter):
    """A resumed run replays the claimed conversation and re-claims nothing."""
    cmd = _resume(adapter, "sid-1")

    assert _flag_value(cmd, "--resume") == "sid-1"
    assert "--session-id" not in cmd, "--session-id on a resume would fight --resume"


@pytest.mark.parametrize("adapter", _ADAPTERS)
def test_fresh_then_resume_then_resume_stays_one_conversation(adapter):
    """The sequence the issue names: continuity must survive repeated heartbeats."""
    session_id = "sid-continuity"
    first, second, third = (
        _fresh(adapter, session_id),
        _resume(adapter, session_id),
        _resume(adapter, session_id),
    )

    assert _flag_value(first, "--session-id") == session_id
    assert _flag_value(second, "--resume") == session_id
    assert _flag_value(third, "--resume") == session_id


@pytest.mark.parametrize("adapter", _ADAPTERS)
def test_fresh_run_can_never_be_built_without_an_id(adapter):
    """session_id is keyword-only and required — omitting it is a TypeError.

    A default would let a caller silently reintroduce the bug, since a fresh run
    with no id looks identical until the *next* heartbeat fails to resume.
    """
    with pytest.raises(TypeError):
        adapter._build_command("claude", None, {}, "prompt")


@pytest.mark.parametrize("adapter", _ADAPTERS)
def test_session_flags_do_not_disturb_the_prompt_terminator(adapter):
    """The claimed id must land before ``--``, not among the positional args."""
    cmd = _fresh(adapter, "sid-1")
    terminator = cmd.index("--")

    assert cmd.index("--session-id") < terminator
    assert cmd[terminator + 1 :] == ["prompt"]
