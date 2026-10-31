# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one risk tier an approval is graded on (#13421).

Four risk vocabularies met at the approval seam: ``command_execution.RiskLevel``
(uppercase, a legacy Redis/SQLite wire format), ``status_enums.Severity`` (lowercase,
ten rungs), ``status_enums.CommandRisk`` (six members, an *allowed-to-run* verdict) and
frontend strings. An approval inbox needs ONE ladder, so :class:`RiskTier` is the
lowercase ``low|medium|high|critical`` subset of ``Severity`` (owner decision
2026-10-12) -- every value is a ``Severity`` value, asserted by test, so it can never
become a fifth vocabulary. ``Severity`` itself is not widened.

Stored data is never rewritten: the terminal's uppercase values are converted here, at
the boundary, by :func:`parse_risk_tier`.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from autobot_shared.status_enums import CommandRisk, Severity


class RiskTier(str, Enum):
    """Ascending approval risk grade; ``str`` so it stores in a String column unchanged."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        """Ascending strictness, derived from declaration order."""
        return _RANK[self]


_RANK: "dict[RiskTier, int]" = {tier: index for index, tier in enumerate(RiskTier)}

_FROM_SEVERITY: "dict[Severity, RiskTier]" = {
    Severity.INFO: RiskTier.LOW,
    Severity.MINIMAL: RiskTier.LOW,
    Severity.LOW: RiskTier.LOW,
    Severity.WARNING: RiskTier.MEDIUM,
    Severity.MEDIUM: RiskTier.MEDIUM,
    Severity.DEGRADED: RiskTier.HIGH,
    Severity.HIGH: RiskTier.HIGH,
    Severity.ERROR: RiskTier.HIGH,
    Severity.CRITICAL: RiskTier.CRITICAL,
}

#: DANGEROUS/FORBIDDEN are *refusals* of a command, not grades of it; an approval that
#: carries one is the most severe thing in the inbox, so both map to the top rung.
_FROM_COMMAND_RISK: "dict[CommandRisk, RiskTier]" = {
    CommandRisk.SAFE: RiskTier.LOW,
    CommandRisk.MODERATE: RiskTier.MEDIUM,
    CommandRisk.HIGH: RiskTier.HIGH,
    CommandRisk.CRITICAL: RiskTier.CRITICAL,
    CommandRisk.DANGEROUS: RiskTier.CRITICAL,
    CommandRisk.FORBIDDEN: RiskTier.CRITICAL,
}


def risk_tier_from_severity(severity: Severity) -> RiskTier:
    """Map a ``Severity``/``RiskLevel``; ``UNKNOWN`` raises -- an emitter must grade, not guess."""
    try:
        return _FROM_SEVERITY[severity]
    except KeyError:
        raise ValueError(f"Severity {severity.value!r} has no approval risk tier; grade it explicitly") from None


def risk_tier_from_command_risk(risk: CommandRisk) -> RiskTier:
    """Map a shell-command verdict onto the approval ladder."""
    return _FROM_COMMAND_RISK[risk]


def parse_risk_tier(value: Any) -> RiskTier:
    """Normalise any producer's risk value to a :class:`RiskTier`.

    Accepts a ``RiskTier``, ``Severity``, ``CommandRisk``, ``command_execution.RiskLevel``
    (matched by member name, so this module needs no backend import) or a string in any case
    (``"HIGH"`` from the terminal wire, ``"high"`` from the frontend). Anything else raises
    ``ValueError`` rather than defaulting to a tier.
    """
    if isinstance(value, RiskTier):
        return value
    if isinstance(value, Severity):
        return risk_tier_from_severity(value)
    if isinstance(value, CommandRisk):
        return risk_tier_from_command_risk(value)
    text = value.name if isinstance(value, Enum) else value
    if isinstance(text, str):
        lowered = text.strip().lower()
        if lowered in RiskTier._value2member_map_:
            return RiskTier(lowered)
    raise ValueError(f"{value!r} is not a risk tier (expected one of {[t.value for t in RiskTier]})")


def presented_risk_tier(value: Any) -> RiskTier | None:
    """The tier to SHOW for a stored risk value, or ``None`` when it has none (#13422).

    For response fields a badge renders, never for gating: an approval decision must use
    :func:`parse_risk_tier`, which refuses to guess. Beyond what that accepts, this reads a
    Severity spelled as a string (``"warning"``, ``"error"``, ``"minimal"``…, which the
    workflow wire carries) through the same ``_FROM_SEVERITY`` map, and gives ``None`` for
    anything ungradable (``"unknown"``, free text) so the caller shows the raw value instead.
    """
    try:
        return parse_risk_tier(value)
    except ValueError:
        pass
    if isinstance(value, str):
        try:
            return risk_tier_from_severity(Severity(value.strip().lower()))
        except ValueError:
            return None
    return None


def presented_risk_tier_value(value: Any) -> str | None:
    """:func:`presented_risk_tier` as the plain string a response dict carries, or ``None``."""
    tier = presented_risk_tier(value)
    return tier.value if tier is not None else None
