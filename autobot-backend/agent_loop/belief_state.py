# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Belief State Updater (MVA-1407)

Maintains the assertion dict on TaskContext: insert new beliefs, reconfirm
existing ones, and detect / record contradictions.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from agent_loop.types import (
    Assertion,
    ContradictionRecord,
    ToolExecutionRef,
)
from autobot_shared.time_utils import now_utc

if TYPE_CHECKING:
    from agent_loop.types import TaskContext


def _slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:80]


def build_extractor_key(tool_name: str, tool_args: dict) -> str | None:
    """Return the primary assertion key for a tool+args pair.

    Matches the key patterns used by EXTRACTOR_REGISTRY extractors so the
    belief cache can check for an existing high-confidence assertion before
    executing the tool.  Returns None when no extractor covers the tool or
    the required argument is absent (MVA-1434).
    """
    if tool_name == "read_file":
        path = tool_args.get("path") or tool_args.get("file_path") or tool_args.get("filename")
        if path:
            return f"read_file:{path}:exists"
    elif tool_name == "web_search":
        query = tool_args.get("query") or tool_args.get("q") or tool_args.get("search_query")
        if query:
            return f"web_search:{_slugify(str(query))}:answered"
    elif tool_name == "run_command":
        from agent_loop.extractors.run_command import _classify_command

        cmd = tool_args.get("command") or tool_args.get("cmd")
        if cmd:
            return f"run_command:exit_code/{_classify_command(str(cmd))}"
    return None


class BeliefStateUpdater:
    """Update TaskContext.assertions from raw tool output."""

    CONTRADICTION_SURFACE_THRESHOLD = 0.3

    def update(
        self,
        ctx: "TaskContext",
        tool_name: str,
        tool_output: Any,
        call_hash: str,
        iteration: int,
    ) -> list[ContradictionRecord]:
        """Extract assertions from tool output and merge into ctx.

        Returns the list of ContradictionRecords produced in this call.
        """
        from agent_loop.extractors import EXTRACTOR_REGISTRY

        extractor = EXTRACTOR_REGISTRY.get(tool_name)
        if extractor is None:
            return []

        extracted: list[tuple[str, Any, float]] = extractor.extract(tool_output)
        ref = ToolExecutionRef(tool_name=tool_name, iteration=iteration, call_hash=call_hash)
        new_contradictions: list[ContradictionRecord] = []

        for key, value, confidence in extracted:
            existing = ctx.assertions.get(key)

            if existing is None:
                ctx.assertions[key] = Assertion(
                    key=key,
                    value=value,
                    confidence=confidence,
                    sources=[ref],
                    confirmed_at=now_utc(),
                )
            elif existing.value == value:
                # Reconfirm: update confidence and append source
                existing.confidence = max(existing.confidence, confidence)
                existing.sources.append(ref)
                existing.confirmed_at = now_utc()
            else:
                # Contradiction
                confidence_delta = abs(confidence - existing.confidence)
                if confidence_delta >= self.CONTRADICTION_SURFACE_THRESHOLD:
                    resolution = "surfaced_to_think"
                elif confidence >= existing.confidence:
                    resolution = "updated"
                else:
                    resolution = "suppressed"

                record = ContradictionRecord(
                    key=key,
                    prior_value=existing.value,
                    prior_confidence=existing.confidence,
                    new_value=value,
                    new_confidence=confidence,
                    iteration=iteration,
                    resolution=resolution,
                )
                ctx.contradictions.append(record)
                new_contradictions.append(record)

                if resolution == "updated":
                    existing.value = value
                    existing.confidence = confidence
                    existing.sources.append(ref)
                    existing.confirmed_at = now_utc()
                    existing.refuted_at = None
                    existing.refutation_source = None
                elif resolution == "surfaced_to_think":
                    # Mark old assertion refuted; new value will surface via contradiction
                    existing.refuted_at = now_utc()
                    existing.refutation_source = ref
                    ctx.assertions[key] = Assertion(
                        key=key,
                        value=value,
                        confidence=confidence,
                        sources=[ref],
                        confirmed_at=now_utc(),
                    )
                # "suppressed" → keep existing, do not update

        return new_contradictions
