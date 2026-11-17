# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bind a person's yes in the chat interrupt to the calls they were shown (#18430).

The interrupt used to show the FIRST call needing approval while a single "yes" approved the whole batch,
and the decision outlived the batch in the checkpointed state. Now the interrupt shows every such call,
and the stored decision carries the HMAC fingerprints of exactly those calls; the dispatch seam lets a call
through line 2 only if its fingerprint is among them. The client's resume payload contributes only
``approved`` and ``reason`` -- never the bound set.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence

from autobot_shared.secret_redaction import redact_nested
from services.ai_line_enforcement import shown_call_fingerprint


def _params(tool_call: Mapping[str, Any]) -> Dict[str, Any]:
    params = tool_call.get("params") or tool_call.get("arguments") or {}
    return params if isinstance(params, dict) else {"value": repr(params)}


def ai_line_calls_shown(shown: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """What the interrupt displays for every call that needs a person: tool and redacted params."""
    return [{"tool": tc.get("name", ""), "params": redact_nested(_params(tc))} for tc in shown]


def calls_summary(calls: Sequence[Mapping[str, Any]]) -> str:
    """The card's one line for calls with no shell command: ``tool {params}`` of the first, ``(+N more)`` (#19957)."""
    first = calls[0]
    params = first.get("params") or {}
    text = (
        f"{first.get('tool', '')} {json.dumps(params, sort_keys=True, default=str)}"
        if params
        else first.get("tool", "")
    )
    return f"{text} (+{len(calls) - 1} more)" if len(calls) > 1 else text


def approval_card(state: Mapping[str, Any], shown: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The interrupt payload the chat UI renders: every shown call, and a one-line command for a non-shell tool."""
    pending, calls = shown[0], ai_line_calls_shown(shown)
    return {
        "type": "command_approval_request",
        "content": pending.get("description", ""),
        "metadata": {
            "command": pending.get("command") or calls_summary(calls),  # #19957: a non-command tool has none
            "host": pending.get("host", ""),
            "risk_level": pending.get("risk_level", "medium"),
            "session_id": state["session_id"],
            "terminal_session_id": state["terminal_session_id"],
            "calls": calls,
        },
    }


def bind_decision(decision: Any, shown: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The decision to keep in state: the client's yes/no, bound to the fingerprints of ``shown``."""
    answer = decision if isinstance(decision, Mapping) else {}
    approved = answer.get("approved") is True
    return {
        "approved": approved,
        "reason": str(answer.get("reason") or ""),
        "bound": [shown_call_fingerprint(tc.get("name", ""), _params(tc)) for tc in shown] if approved else [],
    }
