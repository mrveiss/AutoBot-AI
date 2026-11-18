# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A read-only trace of one chat session, projected from its stored messages (#19963).

Like :mod:`chat_history.turn_projection` this is a pure projection: plain dicts in, plain dicts
out, nothing written. ``chat_sessions`` stays the one system of record; the trace is recomputed
from :meth:`ChatHistoryManager.load_session` on every read.

A turn starts at a user message. Inside it, entries are grouped by ``metadata.iteration`` (the
tag ``chat_workflow`` stamps on every persisted entry of a continuation iteration).

What the stored shape can and cannot say, stated rather than guessed:

* **verdict** -- ``held`` (an approval was requested), ``refused`` (the call was blocked before
  it ran) or ``ran`` (a ``tool_result`` was recorded). Anything else is ``unknown``.
* **result_returned** -- ``no`` only when the call produced no tool output (held and not yet
  approved, or refused). Otherwise ``unknown``: the execution results that are fed to the model
  are collected in memory (``execution_history``) and never written to the session, so a stored
  ``tool_result`` proves the output was *shown*, not that the model *received* it.
* **model** -- stored only on the turn's last prose entry (``_attach_model_and_citations``); an
  iteration reports a model only when its own entry carries one.
* **approval state** -- not in the session at all; it is looked up by id by the caller and passed
  in as *approval_states*. An id with no entry there reads ``unknown``.
"""

from typing import Any, Dict, List, Mapping, Tuple

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.secret_redaction import redact_content, redact_nested, redact_text
from chat_history.message_schema import message_type

UNKNOWN = "unknown"
VERDICT_RAN = "ran"
VERDICT_HELD = "held"
VERDICT_REFUSED = "refused"

#: Approval kinds: the persisted gate (UUID) and the terminal command queue (terminal session id).
KIND_GATE = "gate"
KIND_TERMINAL = "terminal"

#: Longest tool output a trace carries, after redaction. Env-backed; the trace is for diagnosis.
TRACE_OUTPUT_MAX_CHARS = env_int_clamped("AUTOBOT_CHAT_TRACE_OUTPUT_MAX_CHARS", 2000, 1, 100000)

#: Approval states from which the call has not run and will not run without a new decision.
_NO_OUTPUT_STATES = frozenset(
    {"pending", "pending_approval", "rejected", "denied", "withdrawn", "expired", "cancelled", "revision_requested"}
)
#: Metadata flags that mean the call was stopped before it ran.
_REFUSAL_FLAGS = ("blocked", "denied", "ast_violations", "schema_validation_failed", "cancelled_by_hook")
#: The only metadata keys a trace carries as ``params`` (an allowlist, then redacted).
_PARAM_KEYS = ("command", "description", "risk_level", "reasons", "line", "category", "run_id", "bridge")

ApprovalRef = Tuple[str, str]


def _meta(message: Dict[str, Any]) -> Dict[str, Any]:
    metadata = message.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _approval_ref(kind: str, ident: Any) -> ApprovalRef | None:
    return (kind, str(ident)) if ident else None


def _classify(message: Dict[str, Any]) -> Tuple[str, str, ApprovalRef | None] | None:
    """``(tool, verdict, approval_ref)`` for a stored entry that records a tool call, else None."""
    kind, meta = message_type(message, ""), _meta(message)
    tool = meta.get("tool") or meta.get("tool_name")
    if kind == "command_approval_request":
        return "terminal", VERDICT_HELD, _approval_ref(KIND_TERMINAL, meta.get("terminal_session_id"))
    if kind == "approval_required" or meta.get("approval_required"):
        return str(tool or UNKNOWN), VERDICT_HELD, _approval_ref(KIND_GATE, meta.get("approval_id"))
    if not tool:
        return None
    ref = _approval_ref(KIND_GATE, meta.get("approval_id"))
    if any(meta.get(flag) for flag in _REFUSAL_FLAGS) or (kind == "error" and meta.get("line")):
        return str(tool), VERDICT_REFUSED, ref
    if kind == "tool_result":
        return str(tool), VERDICT_RAN, ref
    return None


def approval_refs(messages: List[Dict[str, Any]]) -> List[ApprovalRef]:
    """Every approval id the session's tool calls point at, so the caller can look each up once."""
    refs: List[ApprovalRef] = []
    for message in messages:
        found = _classify(message) if isinstance(message, dict) else None
        if found and found[2] and found[2] not in refs:
            refs.append(found[2])
    return refs


def _scrub(value: Any) -> Any:
    """Name-keyed and content-shaped redaction, into every string: a `command` param can hold `password=x`."""
    if isinstance(value, str):
        return redact_content(redact_text(value))
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _result_returned(verdict: str, state: str) -> str:
    if verdict == VERDICT_REFUSED:
        return "no"
    if verdict == VERDICT_HELD and state in _NO_OUTPUT_STATES:
        return "no"
    return UNKNOWN


def _tool_call(message: Dict[str, Any], states: Mapping[ApprovalRef, str]) -> Dict[str, Any] | None:
    found = _classify(message)
    if found is None:
        return None
    tool, verdict, ref = found
    meta = _meta(message)
    state = states.get(ref, UNKNOWN) if ref else UNKNOWN
    params = _scrub(redact_nested({k: meta[k] for k in _PARAM_KEYS if k in meta}))
    return {
        "id": message.get("id"),
        "timestamp": message.get("timestamp"),
        "tool": tool,
        "verdict": verdict,
        "params": params,
        "output": _scrub(str(message.get("text") or ""))[:TRACE_OUTPUT_MAX_CHARS],
        "approval": {"id": ref[1], "kind": ref[0], "state": state} if ref else None,
        "result_returned": _result_returned(verdict, state),
    }


def _iteration_of(message: Dict[str, Any]) -> int | None:
    value = _meta(message).get("iteration")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _new_turn(index: int, user: Dict[str, Any] | None) -> Dict[str, Any]:
    return {
        "turn": index,
        "user_message_id": user.get("id") if user else None,
        "started_at": user.get("timestamp") if user else None,
        "model": None,
        "iterations": [],
    }


def _iteration(turn: Dict[str, Any], number: int | None) -> Dict[str, Any]:
    for entry in turn["iterations"]:
        if entry["iteration"] == number:
            return entry
    entry = {"iteration": number, "model": None, "replied": False, "tool_calls": []}
    turn["iterations"].append(entry)
    return entry


def _record(turn: Dict[str, Any], message: Dict[str, Any], states: Mapping[ApprovalRef, str]) -> None:
    """Fold one stored assistant/system entry into *turn*."""
    meta = _meta(message)
    call = _tool_call(message, states)
    is_reply = message.get("sender") == "assistant" and meta.get("message_type") == "llm_response"
    if call is None and not is_reply:
        return
    entry = _iteration(turn, _iteration_of(message))
    if call is not None:
        entry["tool_calls"].append(call)
    else:
        entry["replied"] = True
    if meta.get("model"):
        entry["model"] = turn["model"] = str(meta["model"])


def _ordered(turn: Dict[str, Any]) -> Dict[str, Any]:
    """Iterations in numeric order; entries with no iteration tag last."""
    turn["iterations"].sort(key=lambda e: (e["iteration"] is None, e["iteration"] or 0))
    return turn


def project_session_trace(
    messages: List[Dict[str, Any]], approval_states: Mapping[ApprovalRef, str] | None = None
) -> List[Dict[str, Any]]:
    """The session's turns, oldest first. *approval_states* maps ``(kind, id)`` to a current state.

    Pure. *messages* is what ``ChatHistoryManager.load_session`` returns, oldest first.
    """
    states = approval_states or {}
    turns: List[Dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("sender") == "user":
            turns.append(_new_turn(len(turns) + 1, message))
            continue
        if not turns:
            turns.append(_new_turn(1, None))
        _record(turns[-1], message, states)
    return [_ordered(turn) for turn in turns]
