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
from autobot_shared.time_utils import now_utc

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
    timestamp: datetime = field(default_factory=now_utc)

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


def panel_decision(
    probabilities: list[float],
    threshold: float,
    quorum: int,
) -> tuple[VerifierVerdict, int]:
    """Return ``(verdict, refutations)`` for an N-of-M panel. Pure.

    A probability "refutes" when it meets *threshold*; the panel BLOCKs when
    the refutation count reaches *quorum*.
    """
    refutations = sum(1 for p in probabilities if p >= threshold)
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
# Prompt — pure
# ---------------------------------------------------------------------------

_VERIFIER_SYSTEM = (
    "You are an adversarial safety reviewer. "
    "Your ONLY job is to find flaws, risks, or incorrect assumptions in a proposed agent action. "
    "You MUST default to flagging the action as risky when you are uncertain. "
    "Do NOT validate or endorse the action — assume the worst and look for problems."
)

_VERIFIER_USER_TMPL = """\
## Proposed agent action
Tool: {tool_name}
Arguments:
{args_block}

## Agent's stated reason for this action
{reason}

## Your task
Find any flaw, incorrect assumption, unintended side-effect, or security risk
in the proposed action above.  Respond with EXACTLY this format (no extra text):

REFUTATION_PROBABILITY: <float 0.0-1.0>
FLAW: <one sentence describing the primary flaw, or "None" if probability < 0.3>
RATIONALE: <two sentences maximum explaining your assessment>
"""


def _build_verifier_prompt(
    tool_name: str,
    args: dict[str, Any],
    reason: str,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the verifier LLM call."""
    args_block = "\n".join(f"  {k}: {v!r}" for k, v in args.items()) or "  (none)"
    user = _VERIFIER_USER_TMPL.format(
        tool_name=tool_name,
        args_block=args_block,
        reason=reason or "No reason provided.",
    )
    return _VERIFIER_SYSTEM, user


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
) -> tuple[float, str, str | None, str | None]:
    """Call the verifier LLM once.

    Returns (refutation_probability, rationale, provider_name, model_name).
    On error returns (0.0, error_message, None, None) — fail-open so a broken
    verifier does not hard-block the agent.
    """
    from llm_shared.models import LLMRequest

    provider = await _select_verifier_provider(actor_provider)
    if provider is None:
        logger.warning("pre_action_verifier: no provider available — skipping")
        return 0.0, "No verifier provider available.", None, None

    system_prompt, user_prompt = _build_verifier_prompt(tool_name, args, reason)
    request = LLMRequest(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
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
            "pre_action_verifier: LLM call failed (%s: %r) — failing open",
            type(exc).__name__,
            exc,
        )
        return 0.0, f"Verifier LLM error: {exc!r}", None, None

    raw = response.content or ""
    prob = _parse_probability(raw)
    rationale = _parse_rationale(raw)
    return prob, rationale, provider.provider_name, getattr(response, "model", None)


def _parse_probability(raw: str) -> float:
    """Extract REFUTATION_PROBABILITY from the verifier response. Pure."""
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("REFUTATION_PROBABILITY:"):
            value_str = stripped[len("REFUTATION_PROBABILITY:") :].strip()
            try:
                return max(0.0, min(1.0, float(value_str)))
            except ValueError:
                pass
    return 0.5  # Conservative default when parsing fails


def _parse_rationale(raw: str) -> str:
    """Extract RATIONALE from the verifier response. Pure."""
    lines = raw.splitlines()
    collecting = False
    parts: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("RATIONALE:"):
            parts.append(stripped[len("RATIONALE:") :].strip())
            collecting = True
        elif collecting and stripped:
            parts.append(stripped)
    return " ".join(parts) if parts else raw[:300].strip()


# Public aliases — the private names above are kept for the existing test
# import surface (``agent_loop.tests.test_pre_action_verifier``).
parse_probability = _parse_probability
parse_rationale = _parse_rationale


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
        prob, rationale, prov, model = await _call_verifier_once(tool_name, args, reason, self._actor_provider)
        verdict = determine_verdict(prob, threshold)
        result = VerifierResult(
            verdict=verdict,
            refutation_probability=prob,
            rationale=rationale,
            tool_name=tool_name,
            task_id=task_id,
            provider_used=prov,
            model_used=model,
            panel_size=1,
            panel_refutations=1 if verdict == VerifierVerdict.BLOCK else 0,
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

        probs: list[float] = []
        rationales: list[str] = []
        prov: str | None = None
        model: str | None = None

        for r in panel_results:
            if isinstance(r, Exception):
                continue
            prob, rat, p, m = r
            probs.append(prob)
            rationales.append(rat)
            if p:
                prov = p
            if m:
                model = m

        verdict, refutations = panel_decision(probs, threshold, PANEL_QUORUM)
        avg_prob = sum(probs) / len(probs) if probs else 0.0
        rationale = " | ".join(r for r in rationales if r)[:600]
        result = VerifierResult(
            verdict=verdict,
            refutation_probability=avg_prob,
            rationale=rationale,
            tool_name=tool_name,
            task_id=task_id,
            provider_used=prov,
            model_used=model,
            panel_size=n,
            panel_refutations=refutations,
        )
        self._log_result(result, threshold)
        return result

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
    "determine_verdict",
    "panel_decision",
    "threshold_for_tool",
    "hard_block_active",
    "pre_action_verifier_enabled",
    "parse_probability",
    "parse_rationale",
]
