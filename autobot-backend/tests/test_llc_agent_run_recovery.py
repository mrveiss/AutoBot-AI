# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC agent runs must execute and keep their output (#12682, #12683).

Both execution paths of the claude_code adapter were broken, and the recording
path discarded output when a run did succeed:

- fresh session  -> invalid CLI command (missing --verbose)  (#12683)
- resume session -> hard-fails on an unresumable id, forever (#12683)
- successful run -> replay log write aborts on a UUID        (#12682)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# #12683 — the CLI command must be valid
# ---------------------------------------------------------------------------


def _build(resume=None, cfg=None):
    from llc.adapters.claude_code_adapter import ClaudeCodeAdapter

    return ClaudeCodeAdapter._build_command("claude", resume, cfg or {}, "do the thing")


def test_stream_json_print_includes_verbose():
    """Claude Code rejects --print + stream-json without --verbose (#12683)."""
    cmd = _build()

    assert "--verbose" in cmd, (
        "Missing --verbose: the CLI errors with 'When using --print, "
        "--output-format=stream-json requires --verbose' and the run produces nothing."
    )
    assert "--print" in cmd and "stream-json" in cmd


def test_verbose_present_on_resumed_runs_too():
    cmd = _build(resume="abc-123")

    assert "--verbose" in cmd
    assert cmd[cmd.index("--resume") + 1] == "abc-123"


def test_prompt_still_passed_positionally_after_dash_dash():
    """Regression guard: --verbose must not disturb the -- prompt convention."""
    cmd = _build()

    assert cmd[-2] == "--"
    assert cmd[-1] == "do the thing"


def test_fresh_run_still_carries_session_establishment_options():
    cmd = _build(cfg={"model": "sonnet", "max_turns": 7})

    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--max-turns") + 1] == "7"


# ---------------------------------------------------------------------------
# #12683 — an unresumable session must not dead-loop
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "No conversation found with session ID: 63253ddd-7750-4b51-b493-4d21e7f2e9fb",
        "error: no conversation found with session id: abc",
    ],
)
def test_unresumable_session_is_detected(text):
    from llc.adapters.claude_code_adapter import _is_unresumable_session_output

    assert _is_unresumable_session_output(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "rate limit exceeded",
        "Error: connection reset by peer",
        "conversation found",
    ],
)
def test_unrelated_output_does_not_clear_the_session(text):
    """A broad match would drop valid sessions and lose conversation continuity."""
    from llc.adapters.claude_code_adapter import _is_unresumable_session_output

    assert _is_unresumable_session_output(text) is False


# ---------------------------------------------------------------------------
# #12682 — a UUID in the snapshot must not destroy the run record
# ---------------------------------------------------------------------------


def test_json_safe_coerces_uuid():
    from llc.services.replay_service import _json_safe

    run_id = uuid.uuid4()
    assert _json_safe(run_id) == str(run_id)


def test_json_safe_handles_nested_structures():
    """Context is nested; a UUID three levels down broke the write just as well."""
    from llc.services.replay_service import _json_safe

    company = uuid.uuid4()
    payload = {"a": [{"company_id": company}], "b": {"c": {"d": company}}}
    safe = _json_safe(payload)

    assert safe["a"][0]["company_id"] == str(company)
    assert safe["b"]["c"]["d"] == str(company)


def test_json_safe_output_is_actually_serializable():
    """The real assertion: json.dumps must not raise, since that is what aborted the write."""
    import json

    from llc.services.replay_service import _json_safe

    payload = {
        "run_id": uuid.uuid4(),
        "when": datetime(2026, 7, 28, 12, 0, 0),
        "cost": Decimal("1.25"),
        "tags": {"a", "b"},
        "nested": [{"id": uuid.uuid4()}],
    }

    json.dumps(_json_safe(payload))  # must not raise


def test_json_safe_preserves_plain_values():
    from llc.services.replay_service import _json_safe

    payload = {"s": "text", "i": 3, "f": 1.5, "b": True, "n": None, "l": [1, 2]}
    assert _json_safe(payload) == payload


def test_json_safe_falls_back_to_repr_for_exotic_objects():
    """Losing fidelity on one odd value beats losing the entire run log."""
    from llc.services.replay_service import _json_safe

    class Weird:
        def __repr__(self) -> str:
            return "<weird>"

    assert _json_safe({"x": Weird()}) == {"x": "<weird>"}


def test_raw_uuid_payload_is_unserializable_without_the_fix():
    """Pins the original failure mode so the coercion cannot be quietly removed."""
    import json

    with pytest.raises(TypeError, match="not JSON serializable"):
        json.dumps({"run_id": uuid.uuid4()})
