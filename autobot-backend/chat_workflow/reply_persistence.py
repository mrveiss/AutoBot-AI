# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which assistant entries a turn persists, and which model each carries (#21880, #21881).

The rule for "the same answer" (#21880). Both texts are normalised first: Unicode-folded
to lower case, markdown and punctuation reduced to word separators, whitespace collapsed.
Then a model's narration is redundant when, after normalisation, it

* equals an assistant entry already in the turn, or
* is wholly contained, as a run of whole tokens, in the text of a ``respond`` tool entry of the same iteration
  (the narration says nothing the ``respond`` bubble does not). "art" is not contained in "party".

Narration that says something the ``respond`` text does not is kept. Narration that
CONTAINS the ``respond`` text plus more (a lead-in, a trailing line) is kept too: it is
the superset, and dropping it would lose words. That case is an owner ruling (#21880).

Every assistant entry carries the model that produced it (#21881): the model of the
streamed chunk of its own iteration, else the turn's selected model, else ``unknown``.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Dict, Iterable, List

from autobot_shared.text_tokens import word_token_list

UNKNOWN_MODEL = "unknown"
RESPOND_TOOL_TYPE = "respond_tool"


def normalize_reply(text: str | None) -> str:
    """*text* folded for comparison: no markdown, no punctuation, no case, single spaces."""
    return " ".join(word_token_list(unicodedata.normalize("NFKC", text or "")))


def contains_token_run(needle: str, haystack: str) -> bool:
    """True when the normalised *needle* is a contiguous run of whole tokens of the normalised *haystack*."""
    return f" {needle} " in f" {haystack} "


def later_respond_entries(workflow_messages: Iterable[Any], iteration: int) -> List[Dict[str, Any]]:
    """Minimal ``respond`` entries of iterations AFTER *iteration*, so an earlier narration is judged against them.

    The frontend hides narration that any later ``respond`` of the turn repeats; the persisted batch is built
    iteration by iteration, so without these a reload would keep what the live view hid.
    """
    found = []
    for message in workflow_messages:
        meta = getattr(message, "metadata", None) or {}
        if meta.get("message_type") == RESPOND_TOOL_TYPE and (meta.get("iteration") or 0) > iteration:
            found.append(
                {"sender": "assistant", "text": message.content, "metadata": {"message_type": RESPOND_TOOL_TYPE}}
            )
    return found


def _assistant_entries(batch: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [e for e in batch if e.get("sender") == "assistant"]


def _is_respond_entry(entry: Dict[str, Any]) -> bool:
    metadata = entry.get("metadata")
    return isinstance(metadata, dict) and metadata.get("message_type") == RESPOND_TOOL_TYPE


def is_redundant_prose(content: str, batch: Iterable[Dict[str, Any]]) -> bool:
    """True when the prose *content* repeats an assistant entry in *batch* (the rule in the module docstring)."""
    narration = normalize_reply(content)
    if not narration:
        return False
    for entry in _assistant_entries(batch):
        answer = normalize_reply(entry.get("text"))
        if narration == answer:
            return True
        if _is_respond_entry(entry) and contains_token_run(narration, answer):
            return True
    return False


def model_or_unknown(model: Any) -> str:
    """*model* as a non-empty string; ``unknown`` when it is empty or not a string."""
    return model.strip() if isinstance(model, str) and model.strip() else UNKNOWN_MODEL


def stamp_model(entry: Dict[str, Any], model: Any) -> None:
    """Give an assistant *entry* its model unless it already carries one (never replaces, never writes "")."""
    if entry.get("sender") != "assistant":
        return
    metadata = entry.get("metadata")
    if not isinstance(metadata, dict):
        return
    if not isinstance(metadata.get("model"), str) or not metadata["model"].strip():
        entry["metadata"] = {**metadata, "model": model_or_unknown(model)}
