# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Resolve the ownership enforcement mode, and record *how* it was resolved (#15159).

The mode alone is not enough to describe a decision. ``log_only`` is reached two
ways -- an operator (or an unseeded install) sitting in it deliberately, and a
flag store that could not be read at all -- and until #15159 the two produced
byte-identical decision records. The only thing separating them was a
``logger.warning`` emitted here at resolution time: a side effect on another
stream, not a property of the decision. Anything reading the decision (audit
records, metrics, an operator asking why a request was allowed) saw
``log_only_mode`` for both.

That matters because a ``log_only`` window is how the blast radius of flipping
to ``enforced`` gets sized (#14010 AC4). If part of that window was an outage,
the violations counted are of a different population, and nothing in the record
said which.

So resolution returns :class:`ResolvedEnforcementMode` -- the mode *and* whether
it was determined or degraded to -- and the consumer stamps that onto the record
it emits. What the mode *does* is untouched: ``log_only`` remains allow-and-audit
in both cases, deliberately, because denying on a degraded read would turn a flag
blip into a platform-wide read outage (#14010, owner ruling). This module changes
what a decision **records**, never what it **does**.

Split into its own module rather than added to ``session_ownership.py`` for the
same reason ``endpoint_enforcement.py`` was: that file is grandfathered in the
down-only file-size ratchet and may not grow. Mode resolution and its degradation
handling is the cohesive unit, and it is what the marker is a property of.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from fastapi import Request

from autobot_shared.logging_manager import get_logger
from security.endpoint_enforcement import effective_enforcement_mode
from services.feature_flags import EnforcementModeUnavailable

logger = get_logger(__name__)


# What an *undetermined* enforcement mode degrades to (#14010). Deliberately not
# "disabled": an unreachable flag store must not read as "authorization is off".
# log_only keeps every check running and every violation recorded without
# changing what requests succeed, so an outage is loud in the logs and metrics
# instead of silently permissive. Choosing the *default* posture when the flag is
# simply unset is a separate decision and is untouched here.
DEGRADED_ENFORCEMENT_MODE = "log_only"

#: Appended to a decision ``reason`` when the mode was degraded to rather than
#: chosen. A suffix, not a separate field name, so every existing consumer that
#: matches a reason exactly (e.g. ``api/chat.py``'s ``legacy_migration`` check)
#: keeps behaving identically while a new consumer can tell the two apart.
DEGRADED_REASON_SUFFIX = "_degraded"


@dataclass(frozen=True)
class ResolvedEnforcementMode:
    """An enforcement mode together with the provenance of that answer.

    *degraded* is True only when the mode could not be determined and this module
    substituted :data:`DEGRADED_ENFORCEMENT_MODE`. A mode read successfully from
    the flag store is never degraded, including when that read returns
    ``log_only``.
    """

    mode: str
    degraded: bool = False

    def reason(self, chosen_reason: str) -> str:
        """*chosen_reason*, marked if this mode was degraded to rather than chosen.

        Callers pass the reason they would have emitted anyway, so a decision
        record never has to know the suffix convention.
        """
        return f"{chosen_reason}{DEGRADED_REASON_SUFFIX}" if self.degraded else chosen_reason


async def resolve_enforcement_mode(feature_flags) -> ResolvedEnforcementMode:
    """The global enforcement mode, or the degraded substitute when it is undeterminable.

    Every route out of here that is not a successful read is marked ``degraded``,
    so no failure can reach a decision record disguised as a policy choice.
    """
    if not feature_flags:
        # No flags service means `get_feature_flags()` failed at
        # construction — an infrastructure fault, not a policy decision.
        logger.warning(
            "Ownership enforcement mode is UNDETERMINED (no feature-flags service); "
            "degrading to log_only. Checks still run and violations are recorded. "
            "This is not a deliberate 'disabled' (#14010)."
        )
        return ResolvedEnforcementMode(DEGRADED_ENFORCEMENT_MODE, degraded=True)

    try:
        mode_enum = await feature_flags.get_enforcement_mode()
        return ResolvedEnforcementMode(mode_enum.value)
    except EnforcementModeUnavailable as exc:
        logger.warning(
            "Ownership enforcement mode is UNDETERMINED (%s); degrading to log_only. "
            "Checks still run and violations are recorded. This is not a deliberate "
            "'disabled' (#14010).",
            exc,
        )
        return ResolvedEnforcementMode(DEGRADED_ENFORCEMENT_MODE, degraded=True)
    except Exception as e:
        # Anything unexpected is still a failure to determine policy, so it
        # degrades the same way rather than silently disabling every check.
        logger.warning(
            "Ownership enforcement mode could not be resolved (%s); degrading to log_only (#14010).",
            e,
        )
        return ResolvedEnforcementMode(DEGRADED_ENFORCEMENT_MODE, degraded=True)


async def resolve_enforcement_mode_for_request(feature_flags, request: Request) -> ResolvedEnforcementMode:
    """Global mode, tightened by any stricter per-endpoint override (#15086).

    An override can only make the mode stricter, never weaker, so it can move a
    degraded ``log_only`` up to ``enforced`` -- but it cannot make the *resolution*
    any less degraded, and ``degraded`` is carried through unchanged.
    """
    resolved = await resolve_enforcement_mode(feature_flags)
    return replace(resolved, mode=await effective_enforcement_mode(feature_flags, resolved.mode, request))
