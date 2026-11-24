# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The sources of an answer: the steps that fed it, and a deterministic check of the values it quotes (#21976).

Owner requirement: every request carries proof of how it got to its result, without a model call per turn.

* One source per tool step that ran and fed the answer (its tool, redacted arguments, origin, step id and time),
  then the knowledge-base citations. ``llm_training`` appears only when neither exists: an answer built on a tool
  result is never labelled as model memory.
* ``proof`` lists the values the answer quotes (a URL, or a token with a digit) that appear in no executed step of
  this turn, in the user's message or in a retrieved passage. The claim is exactly that: "this exact value does not
  appear in this turn's tool results". Reformatted values and unit conversions (``41°F`` for ``5°C``) read as
  unproven; values from earlier turns read as unproven; non-numeric facts and a relabelled value are not checked.
  A value that is found is never called verified, only "appears in step N".

The stream and the stored entry carry the same list (``attach_answer_proof`` writes it once to the entry; the stream
message is built from the entry).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from async_chat_workflow import WorkflowMessage
from chat_workflow.reply_persistence import RESPOND_TOOL_TYPE, stamp_model
from chat_workflow.step_evidence import STEP_KEY, is_quotable_value, value_digest, value_literals
from chat_workflow.step_outcome import did_execute
from source_attribution import Source, SourceKind, SourceReliability

#: Steps that are bookkeeping, not evidence: the answer tool itself and a tool call that did not parse.
NON_EVIDENCE_TOOLS = frozenset({"respond", "tool_call_parse"})
ANSWER_TYPES = frozenset({RESPOND_TOOL_TYPE, "llm_response"})
_MAX_CHECKED = 50
_EXCERPT_CHARS = 500
#: Where a found value was read: the user's message, or a retrieved knowledge-base passage.
FOUND_IN_USER = "user"
FOUND_IN_KB = "knowledge_base"


def kb_source(citation: Dict[str, Any]) -> Dict[str, Any]:
    """The source entry of one retrieved knowledge-base passage."""
    return {
        "type": SourceKind.KNOWLEDGE_BASE.value,
        "reliability": SourceReliability.HIGH.value,
        "id": citation.get("id", ""),
        "title": citation.get("title") or citation.get("source", ""),
        "source": citation.get("source", ""),
        "score": citation.get("score", 0.0),
        "content": str(citation.get("content") or "")[:_EXCERPT_CHARS],
    }


def llm_training_source(model: str) -> Dict[str, Any]:
    """The honest label of an answer no retrieval or tool step fed."""
    return {
        "type": SourceKind.LLM_TRAINING.value,
        "title": "AI Training Data",
        "model": model,
        "reliability": SourceReliability.MEDIUM.value,
        "source": "LLM",
        "content": "Response generated using LLM training data.",
        "score": 0.5,
    }


def _executed_records(history: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The proof record of each step of *history* that ran and counts as evidence, one per step, in order."""
    records: Dict[str, Dict[str, Any]] = {}
    for result in history or []:
        record = result.get(STEP_KEY) if isinstance(result, dict) else None
        if record and record["tool"] not in NON_EVIDENCE_TOOLS and did_execute(result):
            records.setdefault(record["id"], record)
    return list(records.values())


def _kind(record: Dict[str, Any]) -> SourceKind:
    origin = record["origin"]
    if "command" in origin:
        return SourceKind.SYSTEM_STATE
    if "url" in origin:
        return SourceKind.WEB_PAGE
    return SourceKind.WEB_SEARCH if record["tool"] == "web_search" else SourceKind.TOOL_OUTPUT


def _title(record: Dict[str, Any]) -> str:
    args = record["args"] if isinstance(record["args"], dict) else {}
    detail = next((args[k] for k in ("query", "url", "command") if isinstance(args.get(k), str)), "")
    return f"{record['tool']}: {detail}" if detail else record["tool"]


def step_source(record: Dict[str, Any]) -> Dict[str, Any]:
    """One tool step as a source (``Source.to_dict`` shape, plus the title, link and step id the UI uses)."""
    kind = _kind(record)
    origin = record["origin"]
    link = origin.get("url") or ""  # a search has result links, never one primary link (the UI lists them all)
    reliability = (
        SourceReliability.MEDIUM if kind in (SourceKind.WEB_PAGE, SourceKind.WEB_SEARCH) else SourceReliability.VERIFIED
    )
    source = Source(
        type=kind,
        reliability=reliability,
        content=_title(record),
        timestamp=datetime.fromtimestamp(record["ended_at"], tz=timezone.utc),
        metadata={
            "tool": record["tool"],
            "args": record["args"],
            "origin": origin,
            "started_at": record["started_at"],
            "ended_at": record["ended_at"],
        },
    )
    return {**source.to_dict(), "id": record["id"], "step_id": record["id"], "title": _title(record), "url": link}


def build_answer_sources(
    history: Iterable[Dict[str, Any]], rag_citations: List[Dict[str, Any]] | None, used_knowledge: bool, model: str
) -> List[Dict[str, Any]]:
    """The answer's sources: one per executed tool step, then knowledge-base passages; ``llm_training`` if neither."""
    sources = [step_source(r) for r in _executed_records(history)]
    sources += [kb_source(c) for c in (rag_citations or []) if used_knowledge]
    return sources or [llm_training_source(model)]


def check_quoted_values(
    answer: str, history: Iterable[Dict[str, Any]], user_message: str, kb_citations: List[Dict[str, Any]]
) -> Dict[str, Any] | None:
    """``{"checked", "found": {value: where}, "unproven": [value], "truncated"}``, or None if no tool step ran.

    Only an answer that rests on tool output has values to account for. A value is found when it is among the
    literals of an executed step (its step id), of the user's message, or of a retrieved passage. ``truncated`` is
    true when any step's output was longer than the scan cap or held more quotable values than its digest: the check
    is then partial, and the UI says so. Steps carry hashes of their values (``step_digest``), so each turn's proof
    depends on its own execution history only: nothing is shared between sessions or workers. A value of fewer than
    3 characters or 2 digits is not checked (``is_quotable_value``).
    """
    records = _executed_records(history)
    if not records:
        return None
    partial = any(r.get("partial") or "digest" not in r for r in records)
    homes: List[tuple[str, set]] = [(r["id"], set(r.get("digest") or ())) for r in records]
    homes.append((FOUND_IN_USER, {value_digest(v) for v in value_literals(user_message)}))
    kb_values = (v for c in kb_citations for v in value_literals(str(c.get("content") or "")))
    homes.append((FOUND_IN_KB, {value_digest(v) for v in kb_values}))
    checked = [v for v in value_literals(answer) if is_quotable_value(v)][:_MAX_CHECKED]
    found = {v: next((name for name, digests in homes if value_digest(v) in digests), None) for v in checked}
    return {
        "checked": len(checked),
        "found": {v: where for v, where in found.items() if where},
        "unproven": [v for v, where in found.items() if not where],
        "truncated": partial,
    }


def answer_target(batch: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    """The entry that is the turn's answer: the latest ``respond`` or prose reply, else the last assistant entry.

    The ``respond`` entry wins over earlier narration (it used to lose to it, so the sources landed on the narration).
    """
    assistant = [e for e in batch if e.get("sender") == "assistant"]
    for entry in reversed(assistant):
        if (entry.get("metadata") or {}).get("message_type") in ANSWER_TYPES:
            return entry
    return assistant[-1] if assistant else None


def attach_answer_proof(
    entry: Dict[str, Any],
    *,
    model: str,
    rag_citations: List[Dict[str, Any]] | None,
    used_knowledge: bool,
    history: Iterable[Dict[str, Any]] = (),
    user_message: str = "",
) -> None:
    """Give the answer *entry* its model, its sources (also ``metadata.citations``) and its ``metadata.proof``."""
    history = list(history)
    stamp_model(entry, model)
    sources = build_answer_sources(history, rag_citations, used_knowledge, model)
    proof = check_quoted_values(
        entry.get("text") or "", history, user_message, [c for c in (rag_citations or []) if used_knowledge]
    )
    entry["sources"] = sources
    entry["metadata"] = {
        **(entry.get("metadata") or {}),
        "citations": sources,
        **({"proof": proof} if proof is not None else {}),
    }


def proof_message(entry: Dict[str, Any]) -> WorkflowMessage:
    """The stream message that gives the live answer its sources and proof: the stored entry, under its own id.

    The client keys a bubble by ``metadata.message_id`` and a later message with that id replaces the bubble's
    content, type and metadata, so this carries all three, not only the citations.
    """
    return WorkflowMessage(
        type=entry.get("messageType") or "response",
        content=entry.get("text") or "",
        metadata={**(entry.get("metadata") or {}), "message_id": entry.get("id")},
        id=entry.get("id"),
    )
