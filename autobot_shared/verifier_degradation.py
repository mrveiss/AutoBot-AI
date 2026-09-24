# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Degraded-response policy for the adversarial pre-action verifier (#17306).

A verifier pass can fail to produce a refutation probability in three ways
that are not the same event: a reply arrived carrying no readable
``REFUTATION_PROBABILITY`` (it ran and cannot be read), no verifier provider
was available, or the call raised. ``pre_action_verifier_guard`` used to
express all three as a probability -- ``0.5`` for a parse miss, ``0.0`` for
either error -- and let the threshold compare in ``determine_verdict`` decide
the outcome.

That made the security outcome a numeric coincidence instead of a policy.
With the shipped thresholds and a ``>=`` compare, a parse miss blocked
deploy/mutate/exec/default at ``0.5 >= 0.5`` and passed network mutations at
``0.5 < 0.6``; the comment calling ``0.5`` "conservative" was true of four
action classes and false of the fifth. Because the thresholds are
env-configurable, raising any ``VERIFIER_THRESHOLD_*`` above ``0.5`` moved
that class from fail-closed to fail-open with nothing in the code to say so.
And ``0.0`` on an error sits below every threshold, so "the verifier passed
it" and "the verifier never ran" produced the same PASS.

So a degradation is not a probability here and no longer travels as one. It
is a named state resolved by an explicit switch, recorded on the result, and
reported as ``SKIP`` rather than ``PASS`` when it allows an action through --
``docs/developer/MEASUREMENT_DISCIPLINE.md``: *did not look* must never read
as *found nothing*.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from autobot_shared.env_utils import env_flag, env_str


class VerifierDegradation(str, Enum):
    """Why a verifier pass carries no readable refutation probability."""

    #: The verifier answered and the reply parsed -- not degraded.
    NONE = "none"
    #: A reply arrived with no readable ``REFUTATION_PROBABILITY``.
    UNPARSEABLE = "unparseable"
    #: No verifier provider was available to call.
    NO_PROVIDER = "no_provider"
    #: The call raised or timed out.
    CALL_FAILED = "call_failed"


#: ``block`` (the default) or ``pass``: what an unreadable verifier reply
#: resolves to. Named on purpose -- the old outcome was whatever ``0.5``
#: happened to do against each action class's threshold, which is why raising
#: one threshold could flip that class silently.
ON_UNPARSEABLE_BLOCKS: bool = env_str("VERIFIER_ON_UNPARSEABLE", "block").strip().lower() != "pass"

#: When true, a verifier that never ran blocks the action instead of failing
#: open. Fail-open stays the default: a broken verifier must not brick the
#: agent (#10547). What #17306 adds is the switch for a deployment that would
#: rather refuse, and the SKIP verdict that makes the choice observable.
FAIL_CLOSED: bool = env_flag("VERIFIER_FAIL_CLOSED", False)


def degraded_response_blocks(degradation: VerifierDegradation) -> bool:
    """Return whether *degradation* resolves to a BLOCK under current policy.

    The module constants are read at call time, so a test (or a reload) that
    rebinds ``ON_UNPARSEABLE_BLOCKS``/``FAIL_CLOSED`` is honoured -- the
    ``__getattr__`` proxying in ``agent_loop/pre_action_verifier.py`` exists
    for the same reason: a value captured at import is a stale snapshot.
    """
    if degradation is VerifierDegradation.NONE:
        return False
    if degradation is VerifierDegradation.UNPARSEABLE:
        return ON_UNPARSEABLE_BLOCKS
    return FAIL_CLOSED


def parse_probability(raw: str) -> float | None:
    """Extract ``REFUTATION_PROBABILITY`` from a verifier reply. Pure.

    Returns ``None`` when the field is absent or unreadable -- never a
    stand-in number. The previous ``0.5`` was compared against a threshold by
    the caller, which is the defect #17306 records; a caller now asks
    :func:`degraded_response_blocks` what an unreadable reply means instead.
    """
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("REFUTATION_PROBABILITY:"):
            value_str = stripped[len("REFUTATION_PROBABILITY:") :].strip()
            try:
                return max(0.0, min(1.0, float(value_str)))
            except ValueError:
                pass
    return None


def parse_rationale(raw: str) -> str:
    """Extract ``RATIONALE`` from a verifier reply. Pure."""
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


@dataclass(frozen=True)
class VerifierObservation:
    """One verifier pass: a probability, or a named reason there is none.

    ``probability is None`` and ``degradation is not NONE`` always travel
    together -- that pairing is what stops a degraded pass being read as a
    confident 0.0.
    """

    probability: float | None
    rationale: str
    degradation: VerifierDegradation = VerifierDegradation.NONE
    provider_used: str | None = None
    model_used: str | None = None

    @property
    def degraded(self) -> bool:
        """True when this pass produced no readable probability."""
        return self.degradation is not VerifierDegradation.NONE

    @classmethod
    def from_reply(
        cls,
        raw: str,
        provider_used: str | None = None,
        model_used: str | None = None,
    ) -> "VerifierObservation":
        """Build an observation from a verifier's raw reply text."""
        probability = parse_probability(raw)
        return cls(
            probability=probability,
            rationale=parse_rationale(raw),
            degradation=VerifierDegradation.NONE if probability is not None else VerifierDegradation.UNPARSEABLE,
            provider_used=provider_used,
            model_used=model_used,
        )

    @classmethod
    def failed(cls, degradation: VerifierDegradation, rationale: str) -> "VerifierObservation":
        """Build an observation for a pass that produced no reply at all."""
        return cls(probability=None, rationale=rationale, degradation=degradation)


__all__ = [
    "FAIL_CLOSED",
    "ON_UNPARSEABLE_BLOCKS",
    "VerifierDegradation",
    "VerifierObservation",
    "degraded_response_blocks",
    "parse_probability",
    "parse_rationale",
]
