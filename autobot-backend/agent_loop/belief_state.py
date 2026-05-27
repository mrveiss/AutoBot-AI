# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Belief State Updater (MVA-1407)

Maintains the assertion dict on TaskContext: insert new beliefs, reconfirm
existing ones, and detect / record contradictions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from autobot_shared.time_utils import now_utc

from agent_loop.types import (
    Assertion,
    ContradictionRecord,
    ToolExecutionRef,
)

if TYPE_CHECKING:
    from agent_loop.types import TaskContext

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
