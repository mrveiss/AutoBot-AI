# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Adversarial pre-action verifier decision surface (#10547, extracted #14031).

The verifier machinery lived in ``agent_loop/pre_action_verifier.py`` and ran
nowhere: ``AgentLoop`` has no production caller, so ``pre_action_verifier_enabled``
defaulting to ``True`` (``agent_loop/types.py:266``) read as an active guard while
executing on no request (#13587, #14031). #13590 is the template this follows:
the fact-forcing and repetition guards moved to ``autobot_shared`` and the
production tool seam (``chat_workflow/tool_handler.py``) calls them directly.

Unlike those two guards, the verifier's job is inherently an I/O call — an
independent, differently-prompted model tries to REFUTE a proposed action
before it executes. That call cannot be made pure. What CAN be, and is here:

- Action-class threshold resolution (``threshold_for_tool``).
- Response parsing (``parse_probability`` / ``parse_rationale``).
- Verdict determination from a probability and threshold
  (``determine_verdict`` / ``panel_decision``) — this is what preserves the
  ``HARD_BLOCK`` semantics exactly, and is unit-testable with zero network I/O.

``PreActionVerifier`` composes those pure functions with the LLM call. The
live seam (``chat_workflow/tool_handler.py``) owns invoking it — the side
effect — and only asks the pure functions to interpret the result.

``agent_loop/pre_action_verifier.py`` re-exports this module's public surface
so ``AgentLoop`` and its tests keep working unchanged (the ``fact_forcing``
precedent).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from autobot_shared.env_utils import env_float, env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import CategoryDefaults
from autobot_shared.time_utils import now_utc
from autobot_shared.verifier_degradation import (
    VerifierDegradation,
    VerifierObservation,
    degraded_response_blocks,
    parse_probability,
    parse_rationale,
)
from autobot_shared.verifier_prompt import _build_verifier_prompt  # noqa: F401  (re-export, #17306)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level threshold constants (all env-configurable, never hardcoded)
# ---------------------------------------------------------------------------

#: Minimum refutation probability to block a deploy/infra action.
THRESHOLD_DEPLOY: float = env_float("VERIFIER_THRESHOLD_DEPLOY", 0.5)
#: Minimum refutation probability to block a file/git mutation.
THRESHOLD_MUTATE: float = env_float("VERIFIER_THRESHOLD_MUTATE", 0.5)
#: Minimum refutation probability to block an external HTTP mutating call.
THRESHOLD_NETWORK: float = env_float("VERIFIER_THRESHOLD_NETWORK", 0.6)
#: Minimum refutation probability to block a bash/code-execution call.
THRESHOLD_EXEC: float = env_float("VERIFIER_THRESHOLD_EXEC", 0.5)
#: Fallback threshold for any other action class.
THRESHOLD_DEFAULT: float = env_float("VERIFIER_THRESHOLD_DEFAULT", 0.5)

#: When 1, a BLOCK verdict hard-blocks without escalating to human.
HARD_BLOCK: bool = os.environ.get("VERIFIER_HARD_BLOCK", "0") == "1"

#: Number of verifiers dispatched for N-of-M panel (highest-stakes only).
PANEL_SIZE: int = env_int("VERIFIER_PANEL_SIZE", 1)

#: Minimum verifiers that must refute to trigger a panel block.
PANEL_QUORUM: int = env_int("VERIFIER_PANEL_QUORUM", 1)

#: Whether the verifier is enabled at all.
VERIFIER_ENABLED: bool = os.environ.get("VERIFIER_ENABLED", "1") != "0"

#: Token budget for the verifier LLM call.
VERIFIER_MAX_TOKENS: int = env_int("VERIFIER_MAX_TOKENS", 512)

#: Timeout in seconds for the verifier LLM call.
VERIFIER_TIMEOUT_S: float = env_float("VERIFIER_TIMEOUT_S", 30.0)


# ---------------------------------------------------------------------------
# Action class mapping (tool name -> threshold) — pure
# ---------------------------------------------------------------------------

_DEPLOY_TOOLS = frozenset({"deploy", "ansible", "docker", "kubectl", "helm", "terraform"})
_MUTATE_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "delete_file",
        "move_file",
        "copy_file",
        "create_directory",
        "remove_directory",
        "git_push",
        "git_commit",
        "git_merge",
        "git_rebase",
        "git_reset",
        "git_force_push",
    }
)
_NETWORK_TOOLS = frozenset({"http_post", "http_put", "http_patch", "http_delete", "send_request"})
_EXEC_TOOLS = frozenset(
    {"bash", "shell", "execute_command", "run_command", "terminal", "system_exec", "code_interpreter"}
)


def _threshold_for_tool(tool_name: str) -> float:
    """Return the refutation-probability block threshold for *tool_name*."""
    name = tool_name.lower()
    if name in _DEPLOY_TOOLS or any(name.startswith(t) for t in _DEPLOY_TOOLS):
        return THRESHOLD_DEPLOY
    if name in _MUTATE_TOOLS or any(name.startswith(t) for t in _MUTATE_TOOLS):
        return THRESHOLD_MUTATE
    if name in _NETWORK_TOOLS or any(name.startswith(t) for t in _NETWORK_TOOLS):
        return THRESHOLD_NETWORK
    if name in _EXEC_TOOLS or any(name.startswith(t) for t in _EXEC_TOOLS):
        return THRESHOLD_EXEC
    return THRESHOLD_DEFAULT


# Public alias — the private name above is kept for the existing test import
# surface (``agent_loop.tests.test_pre_action_verifier``).
threshold_for_tool = _threshold_for_tool


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class VerifierVerdict(str, Enum):
    """Decision produced by the adversarial verifier."""

    PASS = "PASS"  # nosec B105  # verifier verdict label, not a credential; no flaw found — allow
    BLOCK = "BLOCK"  # Flaw found — block or escalate to human.
    SKIP = "SKIP"  # Verifier disabled or unavailable — allow through.


@dataclass
class VerifierResult:
    """Full result of one verifier pass."""

    verdict: VerifierVerdict
    refutation_probability: float  # 0.0 = no flaw; 1.0 = definitely flawed
    rationale: str
    tool_name: str
    task_id: str | None = None
    provider_used: str | None = None
    model_used: str | None = None
    panel_size: int = 1
    panel_refutations: int = 0
    #: #17306: why a pass carried no readable probability, if it did not.
    #: ``NONE`` with a SKIP verdict means the verifier was disabled; any other
    #: value means it could not be read, and which one says whether it ran.
    degradation: VerifierDegradation = VerifierDegradation.NONE
    timestamp: datetime = field(default_factory=now_utc)

    def evidence_label(self) -> str:
        """Return the evidence behind this verdict, for a human-facing message.

        ``prob=0.85`` where the verifier was read; ``degradation=call_failed``
        where it was not. A degraded result carries ``0.0`` in
        ``refutation_probability`` as a placeholder, so formatting that number
        would state a reading that never happened (#17306).
        """
        if self.degradation is not VerifierDegradation.NONE:
            return f"degradation={self.degradation.value}"
        return f"prob={self.refutation_probability:.2f}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "refutation_probability": self.refutation_probability,
            "rationale": self.rationale,
            "tool_name": self.tool_name,
            "task_id": self.task_id,
            "provider_used": self.provider_used,
            "model_used": self.model_used,
            "panel_size": self.panel_size,
            "panel_refutations": self.panel_refutations,
            "degradation": self.degradation.value,
            "timestamp": self.timestamp.isoformat(),
        }


# ---------------------------------------------------------------------------
# Verdict determination — pure (this is the HARD_BLOCK-preserving surface)
# ---------------------------------------------------------------------------


def determine_verdict(refutation_probability: float, threshold: float) -> VerifierVerdict:
    """Return BLOCK when *refutation_probability* meets *threshold*, else PASS.

    The single-verifier decision rule, unchanged from the original module:
    ``>=`` is a block. Pure — no I/O, no config reads.
    """
    return VerifierVerdict.BLOCK if refutation_probability >= threshold else VerifierVerdict.PASS


def resolve_verdict(observation: VerifierObservation, threshold: float) -> VerifierVerdict:
    """Return the verdict for one *observation*. Pure (#17306).

    A readable probability goes through :func:`determine_verdict` unchanged --
    that is the ``HARD_BLOCK``-preserving rule. A degraded pass never reaches
    the threshold compare at all: it resolves through the degraded-response
    policy, so the outcome no longer depends on where the action class's
    threshold happens to sit relative to a stand-in number. Allowing one
    through is ``SKIP``, not ``PASS``: the verifier found no flaw only in the
    case where it was actually read.
    """
    if observation.probability is not None:
        return determine_verdict(observation.probability, threshold)
    if degraded_response_blocks(observation.degradation):
        return VerifierVerdict.BLOCK
    return VerifierVerdict.SKIP


def panel_decision(
    probabilities: list[float],
    threshold: float,
    quorum: int,
    degraded_refutations: int = 0,
) -> tuple[VerifierVerdict, int]:
    """Return ``(verdict, refutations)`` for an N-of-M panel. Pure.

    A probability "refutes" when it meets *threshold*; the panel BLOCKs when
    the refutation count reaches *quorum*. *degraded_refutations* counts
    panellists that produced no readable probability and resolve to a block
    under the degraded-response policy (#17306) -- they refute without a
    number, so they cannot be expressed as one in *probabilities*.
    """
    refutations = sum(1 for p in probabilities if p >= threshold) + degraded_refutations
    verdict = VerifierVerdict.BLOCK if refutations >= quorum else VerifierVerdict.PASS
    return verdict, refutations


def hard_block_active() -> bool:
    """Return the current ``HARD_BLOCK`` posture (module constant, env-resolved at import)."""
    return HARD_BLOCK


def pre_action_verifier_enabled() -> bool:
    """Resolve ``pre_action_verifier_enabled`` from the guard profile (#14031).

    Mirrors ``repetition_guard.max_identical_tool_calls()``: profile + per-guard
    env override, falling back to the ``AgentLoopConfig`` dataclass default
    (``True``) when the active profile carries no override — ``standard``
    deliberately carries none, so it reproduces that default.
    """
    from agent_loop.guard_profile import resolve_guard_config_overrides  # noqa: PLC0415
    from agent_loop.types import AgentLoopConfig  # noqa: PLC0415

    overrides = resolve_guard_config_overrides()
    value = overrides.get("pre_action_verifier_enabled", AgentLoopConfig.pre_action_verifier_enabled)
    return bool(value)


# ---------------------------------------------------------------------------
# Provider selection — choose a distinct provider from the actor (I/O)
# ---------------------------------------------------------------------------


async def _select_verifier_provider(actor_provider: str | None) -> Any:
    """Return a provider instance different from *actor_provider* when possible.

    Falls back to any available provider if no distinct one exists.
    Returns None when no provider is available.
    """
    from llm_shared.provider_registry import get_provider_registry

    registry = get_provider_registry()
    all_names: list[str] = [p["name"] for p in registry.list_providers()]

    # Prefer a provider that differs from the actor.
    candidates = [n for n in all_names if n != actor_provider] or all_names
    for name in candidates:
        provider = await registry.get_provider(name)
        if provider is not None:
            return provider
    return None


# ---------------------------------------------------------------------------
# Core verifier call (I/O)
# ---------------------------------------------------------------------------


async def _call_verifier_once(
    tool_name: str,
    args: dict[str, Any],
    reason: str,
    actor_provider: str | None,
) -> VerifierObservation:
    """Call the verifier LLM once and return what came back.

    #17306: a failure returns a named degradation rather than a probability.
    The fail-open *posture* is unchanged by default -- ``VERIFIER_FAIL_CLOSED``
    switches it -- but the caller now resolves it through policy instead of
    comparing ``0.0`` to a threshold, and the result says which happened.
    """
    from llm_shared.models import LLMRequest

    provider = await _select_verifier_provider(actor_provider)
    if provider is None:
        logger.warning("pre_action_verifier: no provider available — degraded (no_provider)")
        return VerifierObservation.failed(VerifierDegradation.NO_PROVIDER, "No verifier provider available.")

    system_prompt, user_prompt = _build_verifier_prompt(tool_name, args, reason)
    request = LLMRequest(
        messages=[
            {"role": CategoryDefaults.ROLE_SYSTEM, "content": system_prompt},
            {"role": CategoryDefaults.ROLE_USER, "content": user_prompt},
        ],
        max_tokens=VERIFIER_MAX_TOKENS,
        temperature=0.1,  # Low temperature for adversarial consistency
        metadata={"purpose": "pre_action_verifier", "tool": tool_name},
    )
    try:
        import asyncio as _asyncio

        response = await _asyncio.wait_for(
            provider.chat_completion(request),
            timeout=VERIFIER_TIMEOUT_S,
        )
    except Exception as exc:
        logger.warning(
            "pre_action_verifier: LLM call failed (%s: %r) — degraded (call_failed), fail_closed=%s",
            type(exc).__name__,
            exc,
            degraded_response_blocks(VerifierDegradation.CALL_FAILED),
        )
        return VerifierObservation.failed(VerifierDegradation.CALL_FAILED, f"Verifier LLM error: {exc!r}")

    return VerifierObservation.from_reply(
        response.content or "",
        provider_used=provider.provider_name,
        model_used=getattr(response, "model", None),
    )


# The parsers live in ``autobot_shared.verifier_degradation`` with the
# degraded-response policy (#17306): ``parse_probability`` returning None on a
# miss and the meaning of that miss are one decision, not two. Both spellings
# stay importable from here for the existing test surface
# (``agent_loop.tests.test_pre_action_verifier``).
_parse_probability = parse_probability
_parse_rationale = parse_rationale


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class PreActionVerifier:
    """Adversarial pre-action verifier integrated into the approval gate.

    Instantiate once per agent loop / dispatch; pass *actor_provider* so the
    verifier can select a distinct model when available.
    """

    def __init__(self, actor_provider: str | None = None) -> None:
        self._actor_provider = actor_provider

    async def verify(
        self,
        tool_name: str,
        args: dict[str, Any],
        reason: str,
        task_id: str | None = None,
        *,
        panel_size: int | None = None,
    ) -> VerifierResult:
        """Run the adversarial verification pass for a proposed action.

        Args:
            tool_name: Name of the tool about to be executed.
            args: Tool arguments dict.
            reason: Reason / context the agent provided for this action.
            task_id: Current task identifier for trajectory recording.
            panel_size: Override the module-level PANEL_SIZE for this call.

        Returns:
            VerifierResult with verdict, rationale, and metadata.
        """
        if not VERIFIER_ENABLED:
            return VerifierResult(
                verdict=VerifierVerdict.SKIP,
                refutation_probability=0.0,
                rationale="Verifier disabled via VERIFIER_ENABLED=0",
                tool_name=tool_name,
                task_id=task_id,
            )

        n = panel_size if panel_size is not None else PANEL_SIZE
        threshold = _threshold_for_tool(tool_name)

        if n <= 1:
            return await self._run_single(tool_name, args, reason, task_id, threshold)
        return await self._run_panel(tool_name, args, reason, task_id, threshold, n)

    async def _run_single(
        self,
        tool_name: str,
        args: dict[str, Any],
        reason: str,
        task_id: str | None,
        threshold: float,
    ) -> VerifierResult:
        """Single-verifier path (default)."""
        observation = await _call_verifier_once(tool_name, args, reason, self._actor_provider)
        verdict = resolve_verdict(observation, threshold)
        result = VerifierResult(
            verdict=verdict,
            # #17306: 0.0 for a degraded pass is a placeholder, not a reading --
            # `degradation` below is what says there was no number to report.
            refutation_probability=observation.probability if observation.probability is not None else 0.0,
            rationale=observation.rationale,
            tool_name=tool_name,
            task_id=task_id,
            provider_used=observation.provider_used,
            model_used=observation.model_used,
            panel_size=1,
            panel_refutations=1 if verdict == VerifierVerdict.BLOCK else 0,
            degradation=observation.degradation,
        )
        self._log_result(result, threshold)
        return result

    async def _run_panel(
        self,
        tool_name: str,
        args: dict[str, Any],
        reason: str,
        task_id: str | None,
        threshold: float,
        n: int,
    ) -> VerifierResult:
        """N-of-M panel path for highest-stakes actions."""
        import asyncio

        tasks = [
            asyncio.create_task(_call_verifier_once(tool_name, args, reason, self._actor_provider)) for _ in range(n)
        ]
        panel_results = await asyncio.gather(*tasks, return_exceptions=True)

        observations: list[VerifierObservation] = []
        for r in panel_results:
            if isinstance(r, Exception):
                # One panellist failing is a degraded panel, not a failed one —
                # it is recorded as a degraded observation so the policy sees
                # it, rather than dropped (#17306); the panel still decides on
                # however many readable probabilities arrived.
                observations.append(VerifierObservation.failed(VerifierDegradation.CALL_FAILED, f"{r!r}"))
                continue
            if isinstance(r, BaseException):
                # `return_exceptions=True` also captures BaseExceptions that are
                # NOT Exceptions — asyncio.CancelledError above all. Swallowing
                # a cancellation would keep this coroutine running after its
                # caller gave up, so it propagates.
                raise r
            observations.append(r)

        result = self._panel_result(observations, tool_name, task_id, threshold, n)
        self._log_result(result, threshold)
        return result

    @staticmethod
    def _panel_result(
        observations: list[VerifierObservation],
        tool_name: str,
        task_id: str | None,
        threshold: float,
        n: int,
    ) -> VerifierResult:
        """Fold panel *observations* into one result. Pure (#17306).

        Degraded panellists cannot be averaged or compared, so they are
        counted through the policy instead: one that blocks is a refutation
        without a number. A panel where nothing was readable and nothing
        blocks is ``SKIP`` — it did not look, which is not the same as having
        found nothing.
        """
        probs = [o.probability for o in observations if o.probability is not None]
        degraded = [o for o in observations if o.probability is None]
        degraded_refutations = sum(1 for o in degraded if degraded_response_blocks(o.degradation))
        verdict, refutations = panel_decision(probs, threshold, PANEL_QUORUM, degraded_refutations)
        if not probs and verdict != VerifierVerdict.BLOCK:
            verdict = VerifierVerdict.SKIP
        return VerifierResult(
            verdict=verdict,
            refutation_probability=sum(probs) / len(probs) if probs else 0.0,
            rationale=" | ".join(o.rationale for o in observations if o.rationale)[:600],
            tool_name=tool_name,
            task_id=task_id,
            provider_used=next((o.provider_used for o in observations if o.provider_used), None),
            model_used=next((o.model_used for o in observations if o.model_used), None),
            panel_size=n,
            panel_refutations=refutations,
            degradation=degraded[0].degradation if degraded and not probs else VerifierDegradation.NONE,
        )

    @staticmethod
    def _log_result(result: VerifierResult, threshold: float) -> None:
        """Log the verifier result at appropriate level."""
        if result.verdict == VerifierVerdict.BLOCK:
            logger.warning(
                "pre_action_verifier: BLOCK tool=%s prob=%.2f threshold=%.2f provider=%s | %s",
                result.tool_name,
                result.refutation_probability,
                threshold,
                result.provider_used,
                result.rationale[:120],
            )
        elif result.degradation is not VerifierDegradation.NONE:
            # #17306: the case that used to be indistinguishable from a real
            # PASS. A metric or log reader can tell "the verifier passed it"
            # from "the verifier never ran" only if this line exists.
            logger.warning(
                "pre_action_verifier: %s tool=%s degradation=%s threshold=%.2f provider=%s — "
                "action allowed WITHOUT a verifier reading",
                result.verdict.value,
                result.tool_name,
                result.degradation.value,
                threshold,
                result.provider_used,
            )
        else:
            logger.info(
                "pre_action_verifier: %s tool=%s prob=%.2f threshold=%.2f provider=%s",
                result.verdict.value,
                result.tool_name,
                result.refutation_probability,
                threshold,
                result.provider_used,
            )


__all__ = [
    "PreActionVerifier",
    "VerifierResult",
    "VerifierVerdict",
    "THRESHOLD_DEPLOY",
    "THRESHOLD_MUTATE",
    "THRESHOLD_NETWORK",
    "THRESHOLD_EXEC",
    "THRESHOLD_DEFAULT",
    "HARD_BLOCK",
    "PANEL_SIZE",
    "PANEL_QUORUM",
    "VERIFIER_ENABLED",
    "VERIFIER_MAX_TOKENS",
    "VERIFIER_TIMEOUT_S",
    "VerifierDegradation",
    "VerifierObservation",
    "degraded_response_blocks",
    "determine_verdict",
    "panel_decision",
    "resolve_verdict",
    "threshold_for_tool",
    "hard_block_active",
    "pre_action_verifier_enabled",
    "parse_probability",
    "parse_rationale",
]
