# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The proof record of one tool step: what ran, with which arguments, where its result came from (#21976).

``begin_step`` is called before a tool call is dispatched; ``DispatchedStep.tag`` stamps its id on each message the
call yields, and ``DispatchedStep.finish`` stamps the call's execution results with one ``step`` record (id, tool,
redacted arguments, start and end time, origin, and the literals the output contains). ``answer_sources`` turns the
records of a turn into the answer's sources. The record rides on the execution result, so it follows the result into the
turn's execution history on both the legacy and the graph path.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List

from autobot_shared.secret_redaction import redact_nested, redact_text
from chat_workflow.step_outcome import exit_code_field
from chat_workflow.tool_call_loop import stamp_call_fingerprint

#: Key of the proof record on an execution result.
STEP_KEY = "step"
#: Result fields that hold a tool's raw output (the keys ``tool_output_spill`` offloads).
OUTPUT_KEYS = ("output", "result", "stdout", "stderr")
_MAX_ARG_CHARS = 500
_MAX_URLS = 10
_MAX_LITERALS = 2000

_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+")
#: A run of characters holding a digit; ``-_/=:,;()[]{}|<>`'"`` and whitespace separate runs ("6.18.33.2-microsoft").
_VALUE_RE = re.compile(r"[^\s,;:()\[\]{}\"'`<>|=/\\_-]*\d[^\s,;:()\[\]{}\"'`<>|=/\\_-]*")
_EDGE = ".*~!?"


def url_list(text: str, limit: int = _MAX_URLS) -> List[str]:
    """The distinct URLs in *text*, in order of appearance, at most *limit*."""
    seen: Dict[str, None] = {}
    for match in _URL_RE.finditer(text or ""):
        seen.setdefault(match.group(0).rstrip(".,;:!?"), None)
    return list(seen)[:limit]


def value_literals(text: str) -> List[str]:
    """The checkable values in *text*: its URLs and every token that contains a digit, distinct, in order.

    Separators are those of ``6.18.33.2-microsoft-standard-WSL2``: the value ``6.18.33.2`` and ``WSL2`` are two
    literals. The same function reads the answer and a tool's output, so the two sides split alike.
    """
    found: Dict[str, None] = {}
    for url in url_list(text, limit=10**6):
        found.setdefault(url, None)
    for token in _VALUE_RE.findall(_URL_RE.sub(" ", text or "")):
        token = token.strip(_EDGE)
        if token:
            found.setdefault(token, None)
    return list(found)


def _output_text(results: Iterable[Dict[str, Any]]) -> str:
    return "\n".join(str(r[k]) for r in results for k in OUTPUT_KEYS if r.get(k))


def safe_args(params: Any) -> Any:
    """*params* through the canonical redactor (``REDACTION_BOUNDARY.md``), each string bounded."""

    def bound(value: Any) -> Any:
        if isinstance(value, str):
            text = redact_text(value)
            return text if len(text) <= _MAX_ARG_CHARS else text[:_MAX_ARG_CHARS] + "..."
        if isinstance(value, dict):
            return {k: bound(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [bound(v) for v in value]
        return value

    return bound(redact_nested(params or {}))


def step_origin(tool: str, params: Dict[str, Any], results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Where the result of a step came from: host and exit code, the page, or the result URLs."""
    first = results[0] if results else {}
    if "command" in first or tool == "execute_command":
        return {"host": first.get("host"), "command": safe_args(first.get("command")), **exit_code_field(first)}
    url = params.get("url") if isinstance(params, dict) else None
    if isinstance(url, str) and url:
        return {"url": url}
    return {"urls": url_list(_output_text(results))}


@dataclass
class DispatchedStep:
    """One dispatched tool call: its id and when it started."""

    step_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: float = field(default_factory=time.time)

    def tag(self, message: Any) -> Any:
        """Stamp this step's id on a yielded message's metadata; return the message."""
        metadata = getattr(message, "metadata", None)
        if isinstance(metadata, dict):
            metadata["step_id"] = self.step_id
        return message

    def finish(self, results: List[Dict[str, Any]], tool_call: Dict[str, Any]) -> None:
        """Fingerprint *results* (#19715) and give each the step's proof record (#21976)."""
        stamp_call_fingerprint(results, tool_call)
        tool, params = str(tool_call.get("name", "")), tool_call.get("params") or {}
        record = {
            "id": self.step_id,
            "tool": tool,
            "args": safe_args(params),
            "started_at": self.started_at,
            "ended_at": time.time(),
            "origin": step_origin(tool, params, results),
            "literals": value_literals(_output_text(results))[:_MAX_LITERALS],
        }
        for result in results:
            result[STEP_KEY] = record


def begin_step() -> DispatchedStep:
    """A new step, started now."""
    return DispatchedStep()
