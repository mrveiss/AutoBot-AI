# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The proof record of one tool step: what ran, with which arguments, where its result came from (#21976).

``begin_step`` is called before a tool call is dispatched; ``DispatchedStep.tag`` stamps its id on each message the
call yields, and ``DispatchedStep.finish`` stamps the call's execution results with one ``step`` record (id, tool,
redacted arguments, start and end time, origin; the literals the output contains are held aside, never streamed).
``answer_sources`` turns the records of a turn into the answer's sources. The record rides on the execution result,
so it follows the result into the turn's execution history on both the legacy and the graph path.
"""

from __future__ import annotations

import re
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List

from autobot_shared.env_utils import env_int
from autobot_shared.secret_redaction import (
    MatchPolicy,
    redact_nested,
    redact_text,
    redact_url_credentials,
    redact_url_userinfo,
)
from chat_workflow.step_outcome import exit_code_field
from chat_workflow.tool_call_loop import stamp_call_fingerprint

#: Key of the proof record on an execution result.
STEP_KEY = "step"
#: Result fields that hold a tool's raw output (the keys ``tool_output_spill`` offloads).
OUTPUT_KEYS = ("output", "result", "stdout", "stderr")
_MAX_ARG_CHARS = 500
_MAX_URLS = 10
#: Most characters of one step's output (or of an answer) read for quotable values; more is read up to this and the
#: proof is marked partial (#21976). Bounds the work on the request path.
SCAN_MAX_CHARS: int = env_int("AUTOBOT_PROOF_SCAN_MAX_CHARS", default=200000)
#: Steps whose literals are held between a step's end and its turn's end; the oldest are dropped first.
KEPT_STEPS: int = env_int("AUTOBOT_PROOF_KEPT_STEPS", default=256)
#: A host that is not a bare label (an IP address, a dotted name) is shown as this, never as itself.
UNLABELLED_HOST = "remote"
_LABEL_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}")
#: Literals of recent steps by step id. Kept out of the execution results: those are streamed to the client.
_LITERALS: "OrderedDict[str, FrozenSet[str]]" = OrderedDict()

_URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+")
#: A run of characters with none of ``-_/=:,;()[]{}|<>`'"`` or whitespace ("6.18.33.2-microsoft" is two runs).
#: Linear: a run is matched as it is; whether it holds a digit is tested after.
_TOKEN_RE = re.compile(r"[^\s,;:()\[\]{}\"'`<>|=/\\_-]+")
_DIGIT_RE = re.compile(r"\d")
_EDGE = ".*~!?"
_MIN_VALUE_CHARS = 3
_MIN_VALUE_DIGITS = 2


def url_list(text: str, limit: int = _MAX_URLS) -> List[str]:
    """The distinct URLs in *text*, in order of appearance, at most *limit*."""
    seen: Dict[str, None] = {}
    for match in _URL_RE.finditer(text or ""):
        seen.setdefault(match.group(0).rstrip(".,;:!?"), None)
    return list(seen)[:limit]


def value_literals(text: str) -> List[str]:
    """The quotable values in *text*: its URLs and every token that contains a digit, distinct, in order.

    Separators are those of ``6.18.33.2-microsoft-standard-WSL2``: the value ``6.18.33.2`` and ``WSL2`` are two
    literals. The same function reads the answer and a tool's output, so the two sides split alike. At most
    ``SCAN_MAX_CHARS`` characters are read.
    """
    text = (text or "")[:SCAN_MAX_CHARS]
    found: Dict[str, None] = {}
    for url in url_list(text, limit=10**6):
        found.setdefault(url, None)
    for token in _TOKEN_RE.findall(_URL_RE.sub(" ", text)):
        token = token.strip(_EDGE)
        if token and _DIGIT_RE.search(token):
            found.setdefault(token, None)
    return list(found)


def is_quotable_value(literal: str) -> bool:
    """Whether a literal can count as evidence either way: a URL, or 3+ characters with 2+ digits.

    ``1`` or ``5°C`` appear in almost any output by chance, so finding them proves nothing and missing them
    flags nothing.
    """
    if _URL_RE.fullmatch(literal):
        return True
    return len(literal) >= _MIN_VALUE_CHARS and len(_DIGIT_RE.findall(literal)) >= _MIN_VALUE_DIGITS


def safe_url(url: str) -> str:
    """*url* with its userinfo and credential-named query params masked (the canonical URL redactors)."""
    return redact_url_userinfo(redact_url_credentials(url, MatchPolicy.BROAD), mask_username=True)


def node_label(host: Any) -> Any:
    """*host* when it is a bare label such as ``main``; ``UNLABELLED_HOST`` for an address or a dotted name."""
    if not isinstance(host, str) or not host:
        return host
    return host if _LABEL_RE.fullmatch(host) else UNLABELLED_HOST


def keep_literals(step_id: str, literals: Iterable[str]) -> None:
    """Hold a step's literals until its turn's answer is checked; the oldest steps are dropped past ``KEPT_STEPS``."""
    _LITERALS[step_id] = frozenset(literals)
    while len(_LITERALS) > max(KEPT_STEPS, 1):
        _LITERALS.popitem(last=False)


def kept_literals(step_id: str) -> FrozenSet[str] | None:
    """The literals held for *step_id*, or None when they are gone (evicted, or the turn resumed elsewhere)."""
    return _LITERALS.get(step_id)


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
        host = node_label(first.get("host"))
        return {"host": host, "command": safe_args(first.get("command")), **exit_code_field(first)}
    url = params.get("url") if isinstance(params, dict) else None
    if isinstance(url, str) and url:
        return {"url": safe_url(url)}
    return {"urls": [safe_url(u) for u in url_list(_output_text(results))]}


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
        text = _output_text(results)
        keep_literals(self.step_id, value_literals(text))
        record = {
            "id": self.step_id,
            "tool": tool,
            "args": safe_args(params),
            "started_at": self.started_at,
            "ended_at": time.time(),
            "origin": step_origin(tool, params, results),
            "partial": len(text) > SCAN_MAX_CHARS,  # more output than the proof reads
        }
        for result in results:
            result[STEP_KEY] = record


def begin_step() -> DispatchedStep:
    """A new step, started now."""
    return DispatchedStep()
