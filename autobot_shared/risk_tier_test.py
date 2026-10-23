# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RiskTier is the one approval risk ladder: a lowercase subset of Severity (#13421)."""

import pytest

from autobot_shared.risk_tier import (
    RiskTier,
    parse_risk_tier,
    risk_tier_from_command_risk,
    risk_tier_from_severity,
)
from autobot_shared.status_enums import CommandRisk, Severity


def test_every_tier_value_is_a_severity_value_so_it_is_never_a_fifth_vocabulary():
    assert {t.value for t in RiskTier} <= {s.value for s in Severity}
    assert [t.value for t in RiskTier] == ["low", "medium", "high", "critical"]


def test_rank_is_ascending():
    assert [t.rank for t in RiskTier] == [0, 1, 2, 3]
    assert RiskTier.LOW.rank < RiskTier.CRITICAL.rank


@pytest.mark.parametrize("severity", [s for s in Severity if s is not Severity.UNKNOWN])
def test_every_gradable_severity_maps_and_never_downgrades_a_rung(severity):
    tier = risk_tier_from_severity(severity)
    if severity.value in {t.value for t in RiskTier}:
        assert tier.value == severity.value


def test_unknown_severity_is_refused_not_guessed():
    with pytest.raises(ValueError, match="grade it explicitly"):
        risk_tier_from_severity(Severity.UNKNOWN)


@pytest.mark.parametrize("risk", list(CommandRisk))
def test_every_command_risk_maps_and_refusals_land_on_the_top_rung(risk):
    tier = risk_tier_from_command_risk(risk)
    assert isinstance(tier, RiskTier)
    if risk.blocks:
        assert tier is RiskTier.CRITICAL


def test_command_risk_ladder_is_monotonic():
    ranked = sorted(CommandRisk, key=lambda r: r.rank)
    tiers = [risk_tier_from_command_risk(r).rank for r in ranked]
    assert tiers == sorted(tiers)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("HIGH", RiskTier.HIGH),
        ("low", RiskTier.LOW),
        (" Critical ", RiskTier.CRITICAL),
        (Severity.MEDIUM, RiskTier.MEDIUM),
    ],
)
def test_parse_accepts_the_terminal_uppercase_wire_and_canonical_forms(value, expected):
    assert parse_risk_tier(value) is expected


def test_parse_accepts_the_backend_command_risk_level_enum_by_member_name():
    from enum import Enum

    class RiskLevel(Enum):  # shape of models.command_execution.RiskLevel (uppercase values)
        MEDIUM = "MEDIUM"

    assert parse_risk_tier(RiskLevel.MEDIUM) is RiskTier.MEDIUM


@pytest.mark.parametrize("bad", ["", "moderate", "unknown", None, 3])
def test_parse_refuses_anything_that_is_not_a_tier(bad):
    with pytest.raises(ValueError):
        parse_risk_tier(bad)
