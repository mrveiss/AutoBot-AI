# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ChatKnowledgeService RAG-firewall inspection helpers.

Issue #16930: ChatKnowledgeService's RAG entry points (smart_retrieve_knowledge,
conversation_aware_retrieve, retrieve_combined_knowledge) each firewall-inspect
their assembled context string through the same chokepoint
(security.content_firewall.inspect_rag_context, #16771 AC5) and, on a
QUARANTINE verdict, scrub every citation dict's raw content the same way the
context string itself was sanitized. Extracted from service.py so the
inspect-then-quarantine sequence lives in one place instead of three (#16930
review split, to keep service.py under its file-size ceiling).
"""

from typing import Any, Dict, List, Sequence, Tuple

from security.content_firewall import FirewallAction, inspect_rag_context

# Replaces a quarantined citation's raw content; the combined context string
# itself is replaced by the firewall's own sanitized ``verdict.content``.
QUARANTINE_MESSAGE = "[FIREWALL: content withheld — moderate injection risk]"


def quarantine_citations(*citation_lists: List[Dict[str, Any]]) -> None:
    """Scrub every citation's raw content in place (QUARANTINE verdict only).

    Each dict's ``"content"`` key is overwritten with QUARANTINE_MESSAGE --
    the combined prompt string was already sanitized by the firewall, but
    citations carry the untrusted original separately (the Sources UI reads
    them from ``session.metadata["last_citations"]``).
    """
    for citations in citation_lists:
        for citation in citations:
            citation["content"] = QUARANTINE_MESSAGE


async def inspect_and_quarantine(
    context: str,
    *,
    context_label: str,
    citation_lists: Sequence[List[Dict[str, Any]]] = (),
) -> Tuple[bool, str]:
    """Firewall-inspect an assembled RAG context string before it reaches the model.

    Every RAG entry point in ChatKnowledgeService shares this chokepoint
    (#16771 AC5): BLOCK and ESCALATE both drop the context -- ESCALATE has
    ``blocked=False`` (it's pending human approval, not a hard refusal), but
    the flagged text must not surface via citations before that approval
    happens, so it gets the same treatment as BLOCK here, not a softer one.
    QUARANTINE keeps the context (sanitized) and every dict in
    ``citation_lists`` has its raw content scrubbed too, since only the
    combined string was sanitized by the firewall itself.

    Returns ``(should_block, context)``. ``should_block`` True means the
    caller must return its own empty-result tuple immediately;
    ``citation_lists`` were left untouched. False means ``context`` is either
    unchanged (empty input, or a PASS verdict's own content) or the
    firewall's QUARANTINE replacement, and ``citation_lists`` were quarantined
    in place if the verdict was QUARANTINE.
    """
    if not context:
        return False, context
    verdict = await inspect_rag_context(context, context_label=context_label)
    if verdict.blocked or verdict.escalated:
        return True, ""
    if verdict.action == FirewallAction.QUARANTINE:
        quarantine_citations(*citation_lists)
    return False, verdict.content
