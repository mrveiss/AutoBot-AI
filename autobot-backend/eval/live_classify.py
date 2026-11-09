# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Failure categories for a live chat run (#20843).

Every category is decided by a detector the chat workflow already owns; nothing here re-implements one:

- ``malformed_tool_call`` -- the tool-call markers the handler detects are present but the handler's own
  extractor parses fewer calls than the markers announce (``ToolHandlerMixin._detect_tool_call_markers`` /
  ``_extract_tool_calls_from_text``, grammar in ``chat_workflow.tool_call_grammar``).
- ``unknown_tool`` -- the dispatcher answered with ``metadata.message_type == "unknown_tool"``
  (``tool_dispatch_guards.unknown_tool_error``).
- ``loop_stall`` -- the loop detector reached ``_LOOP_ABORT_THRESHOLD``, the continuation cap was reached while the
  graph still wanted to continue, or the run timed out.
- ``false_done`` -- a final answer while the golden's success criteria fail. A golden with no criteria falls back to
  a heuristic (every tool attempt errored, yet the run answered "completed"), and that is reported as heuristic.
- ``unsupported_claim`` -- a substantive answer to a golden that needs grounding, with no knowledge used and no
  citation, or an optional pinned judge saying the answer is unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.env_utils import env_registered
from chat_workflow import limits
from chat_workflow.tool_call_grammar import TOOL_CALL_OPENING_RE, TOOL_CALL_PATTERN
from chat_workflow.tool_call_loop import _LOOP_ABORT_THRESHOLD
from chat_workflow.tool_handler import ToolHandlerMixin

MALFORMED_TOOL_CALL = "malformed_tool_call"
UNKNOWN_TOOL = "unknown_tool"
LOOP_STALL = "loop_stall"
FALSE_DONE = "false_done"
UNSUPPORTED_CLAIM = "unsupported_claim"
#: Not in ``CATEGORIES``: it needs the golden's allowlist, so the candidate adds it (``eval.live.forbidden_tools``).
FORBIDDEN_TOOL = "forbidden_tool"
CATEGORIES = (MALFORMED_TOOL_CALL, UNKNOWN_TOOL, LOOP_STALL, FALSE_DONE, UNSUPPORTED_CLAIM)

#: Task classes whose answers must rest on retrieved knowledge (the grounding signal applies to them only).
GROUNDED_TASK_CLASSES = frozenset({"knowledge_qa", "troubleshooting"})
#: An answer shorter than this many words is not a claim worth grounding (a refusal, an acknowledgement).
SUBSTANTIVE_MIN_WORDS = env_registered("AUTOBOT_EVAL_SUBSTANTIVE_MIN_WORDS")

_PARSER = ToolHandlerMixin()  # the detectors read no instance state; the chat handler stays the only parser


@dataclass
class LiveRunRecord:
    """What one headless chat turn left behind: the messages streamed and the final graph state."""

    final_text: str = ""
    final_status: str = "completed"
    tool_sequence: List[str] = field(default_factory=list)
    raw_responses: List[str] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    execution_history: List[Dict[str, Any]] = field(default_factory=list)
    tool_loop_count: int = 0
    iteration_count: int = 0
    should_continue: bool = False
    used_knowledge: bool = False
    rag_citations: List[Any] = field(default_factory=list)
    timed_out: bool = False
    error: str | None = None
    #: ``SuccessCriteriaEvaluator`` verdict (``full``/``partial``/``failed``); None when the golden has no criteria.
    criteria_overall: str | None = None
    #: The golden's task class needs grounded answers (set by the candidate from ``GROUNDED_TASK_CLASSES``).
    grounding_required: bool = False
    #: The golden's grounding criteria (``resource_exists`` on ``grounded``) held; None when it declares none.
    grounding_ok: bool | None = None
    #: A pinned judge's verdict that the answer is unsupported; None when no judge ran.
    judge_unsupported: bool | None = None
    #: Tokens the provider reported for the run; None when it reported none. Never estimated.
    tokens: int | None = None


def _unterminated(text: str) -> bool:
    """True when the text opens more tool-call tags than the handler's grammar finds complete calls in it."""
    return len(TOOL_CALL_OPENING_RE.findall(text)) > sum(1 for _ in TOOL_CALL_PATTERN.finditer(text))


def _malformed(texts: List[str]) -> bool:
    """True when a response announces a tool call the handler's own extractor cannot fully parse.

    That covers an unparseable call and an unterminated one following valid calls.
    """
    for text in texts:
        announced, _ = _PARSER._detect_tool_call_markers(text or "")
        if not announced:
            continue
        calls, matches = _PARSER._extract_tool_calls_from_text(text)
        if not calls or len(calls) < matches or _unterminated(text):
            return True
    return False


def _unknown_tool(messages: List[Dict[str, Any]]) -> bool:
    return any((m.get("metadata") or {}).get("message_type") == "unknown_tool" for m in messages)


def _stalled(record: LiveRunRecord) -> bool:
    capped = record.should_continue and record.iteration_count >= limits.MAX_CONTINUATION_ITERATIONS
    return record.timed_out or capped or record.tool_loop_count >= _LOOP_ABORT_THRESHOLD


def _every_attempt_errored(record: LiveRunRecord) -> bool:
    history = record.execution_history
    return bool(history) and all(entry.get("status") == "error" for entry in history)


def _false_done(record: LiveRunRecord) -> bool:
    if not record.final_text.strip() or record.final_status != "completed":
        return False
    if record.criteria_overall is not None:
        return record.criteria_overall != "full"
    return _every_attempt_errored(record)


def _unsupported(record: LiveRunRecord) -> bool:
    if record.judge_unsupported or record.grounding_ok is False:
        return True
    if not record.grounding_required or len(record.final_text.split()) < SUBSTANTIVE_MIN_WORDS:
        return False
    return not record.used_knowledge and not record.rag_citations


def classify_failures(record: LiveRunRecord) -> List[str]:
    """The failure categories of *record*, in ``CATEGORIES`` order; empty for a clean run."""
    found = {
        MALFORMED_TOOL_CALL: _malformed(record.raw_responses),
        UNKNOWN_TOOL: _unknown_tool(record.messages),
        LOOP_STALL: _stalled(record),
        FALSE_DONE: _false_done(record),
        UNSUPPORTED_CLAIM: _unsupported(record),
    }
    return [name for name in CATEGORIES if found[name]]


def is_heuristic(record: LiveRunRecord, category: str) -> bool:
    """True when *category* rests on a heuristic rather than a criterion the golden declared."""
    return category == FALSE_DONE and record.criteria_overall is None
