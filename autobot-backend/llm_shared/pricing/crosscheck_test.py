# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the LiteLLM/OpenRouter price cross-check (#16229)."""

from llm_shared.pricing.crosscheck import cross_check, match_key
from llm_shared.pricing.sources import ModelPricing

_TOL = 10.0


def _mp(provider, model_id, inp, out, source):
    return ModelPricing(provider=provider, model_id=model_id, input_per_1m=inp, output_per_1m=out, source=source)


def _primary(model_id, provider, inp, out):
    return {model_id: _mp(provider, model_id, inp, out, "litellm")}


def _secondary(full_id, inp, out):
    vendor, name = full_id.split("/", 1)
    return {full_id: _mp(vendor, name, inp, out, "openrouter")}


def test_the_two_catalogues_spell_one_model_the_same_way_after_normalising():
    assert match_key("anthropic", "claude-haiku-4.5") == match_key("anthropic", "claude-haiku-4-5")
    assert match_key("google", "gemini-2.5-pro") == match_key("gemini", "gemini-2.5-pro")


def test_matching_prices_within_tolerance_agree():
    report, verdicts, only_secondary = cross_check(
        _primary("claude-haiku-4-5", "anthropic", 1.0, 5.0),
        _secondary("anthropic/claude-haiku-4.5", 1.05, 5.0),
        _TOL,
    )
    assert (report.compared, report.agreed, report.disagreed) == (1, 1, [])
    assert verdicts == {"claude-haiku-4-5": "agree"}
    assert only_secondary == []


def test_a_difference_beyond_tolerance_is_flagged_not_resolved():
    report, verdicts, _ = cross_check(
        _primary("claude-haiku-4-5", "anthropic", 1.0, 5.0),
        _secondary("anthropic/claude-haiku-4.5", 1.5, 5.0),
        _TOL,
    )
    assert report.compared == 1 and report.agreed == 0
    assert verdicts == {"claude-haiku-4-5": "disagree"}
    [flag] = report.disagreed
    assert (flag["field"], flag["primary_value"], flag["secondary_value"], flag["percent"]) == (
        "input_per_1m",
        1.0,
        1.5,
        33.3,
    )


def test_a_model_only_one_catalogue_lists_is_never_counted_as_agreement():
    """The denominator matters: 'no disagreements' over zero comparisons checked nothing."""
    report, verdicts, only_secondary = cross_check(
        _primary("gpt-4o", "openai", 2.5, 10.0), _secondary("anthropic/claude-haiku-4.5", 1.0, 5.0), _TOL
    )
    assert (report.compared, report.agreed, report.only_primary, report.only_secondary) == (0, 0, 1, 1)
    assert verdicts == {"gpt-4o": "single"}
    assert only_secondary == ["anthropic/claude-haiku-4.5"]


def test_reseller_routes_and_variants_are_counted_as_not_comparable():
    report, verdicts, only_secondary = cross_check(
        _primary("bedrock/anthropic.claude-haiku", "bedrock", 1.0, 5.0),
        _secondary("anthropic/claude-haiku-4.5:free", 0.0, 0.0),
        _TOL,
    )
    assert (report.not_comparable, report.compared) == (2, 0)
    assert verdicts == {} and only_secondary == []


def test_one_name_under_two_vendors_is_not_compared():
    report, _, _ = cross_check(_primary("m-1", "openai", 1.0, 1.0), _secondary("anthropic/m-1", 9.0, 9.0), _TOL)
    assert report.compared == 0
