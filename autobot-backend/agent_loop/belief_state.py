# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Belief State — GH#6629

Manages the agent's belief about world state as a keyed dict of Assertions.
Separate from the execution log: TaskContext records what the agent DID;
BeliefState records what the agent KNOWS.

Update flow:
  tool result → Extractor.extract() → BeliefState.update() → think prompt
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

from agent_loop.types import (
    Assertion,
    ContradictionRecord,
    ToolExecutionRef,
)

if TYPE_CHECKING:
    from agent_loop.types import TaskContext

logger = get_logger(__name__)


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


class BeliefState:
    """Manages structured assertions about world state.

    Separate from execution log: wraps the assertions/contradictions that are
    stored on TaskContext, providing query and summarization methods for
    injecting facts into think prompts.

    Thread-safety: not thread-safe — caller must serialise updates if running
    parallel tool executors. The agent loop processes extractions sequentially
    after each tool batch completes.
    """

    def __init__(
        self,
        assertions: dict[str, Assertion] | None = None,
        contradictions: list[ContradictionRecord] | None = None,
    ) -> None:
        self.assertions: dict[str, Assertion] = assertions or {}
        self.contradictions: list[ContradictionRecord] = contradictions or []

    @classmethod
    def from_task_context(cls, task_context: "TaskContext") -> "BeliefState":
        """Wrap the assertions/contradictions already stored on TaskContext.

        GH#6629: TaskContext is a pure execution log. BeliefState wraps the
        belief-state fields (assertions, contradictions) and provides query
        and summarization methods without mutating the original.
        """
        return cls(
            assertions=task_context.assertions,
            contradictions=task_context.contradictions,
        )

    def get(self, key: str) -> Assertion | None:
        """Return the active assertion for *key*, or None."""
        a = self.assertions.get(key)
        return a if (a is not None and a.is_active) else None

    def get_value(self, key: str, default: Any = None) -> Any:
        """Return the value of the active assertion for *key*, or *default*."""
        a = self.get(key)
        return a.value if a is not None else default

    def active_assertions(self) -> list[Assertion]:
        """Return all active assertions, sorted by key."""
        return sorted([a for a in self.assertions.values() if a.is_active], key=lambda a: a.key)

    def summary(self, max_contradictions: int = 3) -> str:
        """Return a human-readable belief summary for injection into think prompts.

        Includes active assertions with confidence, and recent contradictions
        flagged as uncertain for agent verification.
        """
        active = self.active_assertions()

        if not active and not self.contradictions:
            return "No established beliefs yet."

        lines: list[str] = []

        if active:
            lines.append("## Established Beliefs")
            for a in active:
                conf_pct = f"{a.confidence:.0%}"
                lines.append(f"- `{a.key}` = {a.value!r}  (confidence: {conf_pct})")

        recent = self.contradictions[-max_contradictions:]
        if recent:
            lines.append("")
            lines.append("## Recent Contradictions (agent should verify)")
            for c in recent:
                lines.append(
                    f"- `{c.key}`: previously {c.prior_value!r}, "
                    f"now {c.new_value!r} — treat as uncertain"
                )

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to dictionary for events/logging."""
        return {
            "assertions": {k: v.to_dict() for k, v in self.assertions.items()},
            "contradictions": [c.to_dict() for c in self.contradictions],
        }


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
