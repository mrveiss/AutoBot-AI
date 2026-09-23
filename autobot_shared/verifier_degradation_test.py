# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Degraded verifier responses resolve by policy, not by threshold luck (#17306).

The defect these pin: a parse miss returned ``0.5`` and the caller compared it
to the action class's threshold, so with the shipped values it blocked
deploy/mutate/exec/default (``0.5 >= 0.5``) and **passed** network mutations
(``0.5 < 0.6``) -- and raising any ``VERIFIER_THRESHOLD_*`` above ``0.5``
moved that class to fail-open with nothing to say so. The error paths
returned ``0.0``, which no threshold can meet, so "the verifier passed it"
and "the verifier never ran" were the same PASS.

So the two properties asserted here are: every action class resolves a
degraded response the same way, and that way does not move when a threshold
moves. The second is the one that could not previously be written down,
because the outcome *was* the threshold comparison.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared import pre_action_verifier_guard as guard
from autobot_shared import verifier_degradation as degradation_mod
from autobot_shared.pre_action_verifier_guard import (
    PreActionVerifier,
    VerifierVerdict,
    panel_decision,
    resolve_verdict,
    threshold_for_tool,
)
from autobot_shared.verifier_degradation import (
    VerifierDegradation,
    VerifierObservation,
    degraded_response_blocks,
    parse_probability,
)

#: One tool per action class, including the one the old default let through.
_TOOLS_BY_CLASS = ("deploy", "write_file", "http_post", "bash", "some_exotic_tool")

_UNPARSEABLE = VerifierObservation.from_reply("I am not going to answer in your format.")


# ------------------------------------------------------------------ parsing


def test_parse_probability_returns_none_on_a_miss():
    """Not 0.5: a missing reading is not a reading of one-half."""
    assert parse_probability("nothing here") is None
    assert parse_probability("REFUTATION_PROBABILITY: not-a-number") is None


def test_parse_probability_still_reads_and_clamps_a_real_value():
    assert parse_probability("REFUTATION_PROBABILITY: 0.85") == pytest.approx(0.85)
    assert parse_probability("REFUTATION_PROBABILITY: 1.5") == pytest.approx(1.0)
    assert parse_probability("REFUTATION_PROBABILITY: -0.2") == pytest.approx(0.0)


def test_an_unreadable_reply_is_marked_unparseable():
    assert _UNPARSEABLE.degraded is True
    assert _UNPARSEABLE.degradation is VerifierDegradation.UNPARSEABLE
    assert _UNPARSEABLE.probability is None


def test_a_readable_reply_is_not_degraded():
    observation = VerifierObservation.from_reply("REFUTATION_PROBABILITY: 0.9\nRATIONALE: the path is wrong.")

    assert observation.degraded is False
    assert observation.probability == pytest.approx(0.9)
    assert "path is wrong" in observation.rationale


# ------------------------------------------------------- the policy itself


def test_unparseable_blocks_by_default():
    assert degraded_response_blocks(VerifierDegradation.UNPARSEABLE) is True


def test_errors_fail_open_by_default():
    assert degraded_response_blocks(VerifierDegradation.NO_PROVIDER) is False
    assert degraded_response_blocks(VerifierDegradation.CALL_FAILED) is False


def test_fail_closed_switch_turns_the_error_paths_into_blocks():
    with patch.object(degradation_mod, "FAIL_CLOSED", True):
        assert degraded_response_blocks(VerifierDegradation.NO_PROVIDER) is True
        assert degraded_response_blocks(VerifierDegradation.CALL_FAILED) is True


def test_on_unparseable_pass_switch_stops_it_blocking():
    with patch.object(degradation_mod, "ON_UNPARSEABLE_BLOCKS", False):
        assert degraded_response_blocks(VerifierDegradation.UNPARSEABLE) is False


def test_a_readable_response_is_never_a_degradation():
    assert degraded_response_blocks(VerifierDegradation.NONE) is False


# ------------------------------------------- the defect: per action class


@pytest.mark.parametrize("tool_name", _TOOLS_BY_CLASS)
def test_unparseable_reply_blocks_every_action_class(tool_name):
    """`http_post` is the one the 0.5-vs-0.6 coincidence used to pass."""
    verdict = resolve_verdict(_UNPARSEABLE, threshold_for_tool(tool_name))

    assert verdict == VerifierVerdict.BLOCK


@pytest.mark.parametrize("threshold", [0.0, 0.5, 0.6, 0.9, 1.0])
def test_the_unparseable_outcome_does_not_move_with_the_threshold(threshold):
    """AC2: raising a VERIFIER_THRESHOLD_* cannot flip this class to fail-open.

    There is no parse-miss default left to sit above or below a threshold --
    a degraded response never reaches the compare -- so the coupling the
    issue describes is removed rather than validated.
    """
    assert resolve_verdict(_UNPARSEABLE, threshold) == VerifierVerdict.BLOCK


@pytest.mark.parametrize("threshold", [0.0, 0.5, 0.6, 0.9, 1.0])
def test_an_error_path_is_equally_threshold_independent(threshold):
    observation = VerifierObservation.failed(VerifierDegradation.CALL_FAILED, "boom")

    assert resolve_verdict(observation, threshold) == VerifierVerdict.SKIP


def test_a_readable_probability_still_uses_the_threshold():
    """The HARD_BLOCK-preserving rule is untouched for real readings."""
    readable = VerifierObservation(probability=0.55, rationale="r")

    assert resolve_verdict(readable, 0.5) == VerifierVerdict.BLOCK
    assert resolve_verdict(readable, 0.6) == VerifierVerdict.PASS


# ------------------------------------- allowing through is SKIP, not PASS


def test_allowing_a_degraded_response_through_is_skip():
    """PASS means "no flaw found"; nothing was found because nothing was read."""
    for cause in (VerifierDegradation.NO_PROVIDER, VerifierDegradation.CALL_FAILED):
        observation = VerifierObservation.failed(cause, "degraded")

        assert resolve_verdict(observation, 0.5) == VerifierVerdict.SKIP


def test_unparseable_under_a_pass_policy_is_skip_too():
    with patch.object(degradation_mod, "ON_UNPARSEABLE_BLOCKS", False):
        assert resolve_verdict(_UNPARSEABLE, 0.5) == VerifierVerdict.SKIP


def test_fail_closed_makes_an_unavailable_verifier_block():
    observation = VerifierObservation.failed(VerifierDegradation.NO_PROVIDER, "none available")

    with patch.object(degradation_mod, "FAIL_CLOSED", True):
        assert resolve_verdict(observation, 0.5) == VerifierVerdict.BLOCK


# ------------------------------------------------------------------- panel


def test_panel_counts_a_degraded_panellist_as_a_refutation():
    """The degraded panellist is the only refutation: 0.1 does not meet 0.5."""
    verdict, refutations = panel_decision([0.1], threshold=0.5, quorum=1, degraded_refutations=1)

    assert (verdict, refutations) == (VerifierVerdict.BLOCK, 1)


def test_a_degraded_panellist_alone_does_not_reach_a_quorum_of_two():
    verdict, refutations = panel_decision([0.1], threshold=0.5, quorum=2, degraded_refutations=1)

    assert (verdict, refutations) == (VerifierVerdict.PASS, 1)


def test_panel_without_degraded_panellists_is_unchanged():
    verdict, refutations = panel_decision([0.9, 0.1], threshold=0.5, quorum=1)

    assert (verdict, refutations) == (VerifierVerdict.BLOCK, 1)


def test_a_panel_that_read_nothing_and_blocks_nothing_is_skip():
    observations = [
        VerifierObservation.failed(VerifierDegradation.CALL_FAILED, "boom"),
        VerifierObservation.failed(VerifierDegradation.NO_PROVIDER, "none"),
    ]

    result = PreActionVerifier._panel_result(observations, "bash", None, 0.5, 2)

    assert result.verdict == VerifierVerdict.SKIP
    assert result.degradation is VerifierDegradation.CALL_FAILED
    assert result.refutation_probability == pytest.approx(0.0)


def test_a_panel_with_one_readable_probability_still_decides_on_it():
    observations = [
        VerifierObservation(probability=0.9, rationale="flawed"),
        VerifierObservation.failed(VerifierDegradation.CALL_FAILED, "boom"),
    ]

    result = PreActionVerifier._panel_result(observations, "bash", None, 0.5, 2)

    assert result.verdict == VerifierVerdict.BLOCK
    assert result.degradation is VerifierDegradation.NONE


# --------------------------------------------- the result carries the cause


def test_the_result_reports_the_degradation_it_resolved():
    observation = VerifierObservation.failed(VerifierDegradation.CALL_FAILED, "boom")

    result = PreActionVerifier._panel_result([observation], "deploy", "task-1", 0.5, 1)

    assert result.to_dict()["degradation"] == "call_failed"
    assert result.evidence_label() == "degradation=call_failed"


def test_a_real_reading_labels_the_probability():
    result = PreActionVerifier._panel_result(
        [VerifierObservation(probability=0.42, rationale="r")], "deploy", None, 0.5, 1
    )

    assert result.evidence_label() == "prob=0.42"
    assert result.to_dict()["degradation"] == "none"


# ----------------------------------------- the call itself maps its failures


class TestCallVerifierOnce:
    """The three degradation causes as `_call_verifier_once` produces them."""

    @pytest.mark.asyncio
    async def test_no_provider_available(self):
        with patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=None)):
            observation = await guard._call_verifier_once("bash", {}, "reason", None)

        assert observation.degradation is VerifierDegradation.NO_PROVIDER
        assert observation.probability is None

    @pytest.mark.asyncio
    async def test_provider_exception(self):
        provider = MagicMock()
        provider.provider_name = "fake"
        provider.chat_completion = AsyncMock(side_effect=RuntimeError("upstream down"))

        with patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=provider)):
            observation = await guard._call_verifier_once("bash", {}, "reason", None)

        assert observation.degradation is VerifierDegradation.CALL_FAILED
        assert "upstream down" in observation.rationale

    @pytest.mark.asyncio
    async def test_unreadable_reply(self):
        provider = MagicMock()
        provider.provider_name = "fake"
        provider.chat_completion = AsyncMock(return_value=MagicMock(content="no format here", model="m"))

        with patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=provider)):
            observation = await guard._call_verifier_once("bash", {}, "reason", None)

        assert observation.degradation is VerifierDegradation.UNPARSEABLE
        assert observation.provider_used == "fake"

    @pytest.mark.asyncio
    async def test_readable_reply(self):
        provider = MagicMock()
        provider.provider_name = "fake"
        provider.chat_completion = AsyncMock(
            return_value=MagicMock(content="REFUTATION_PROBABILITY: 0.7\nRATIONALE: risky.", model="m")
        )

        with patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=provider)):
            observation = await guard._call_verifier_once("bash", {}, "reason", None)

        assert observation.degradation is VerifierDegradation.NONE
        assert observation.probability == pytest.approx(0.7)


class TestVerifyEndToEnd:
    """`verify()` composes the pieces: a broken verifier never reads as PASS."""

    @pytest.mark.asyncio
    async def test_a_broken_verifier_skips_rather_than_passing(self):
        with (
            patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=None)),
            patch.object(guard, "VERIFIER_ENABLED", True),
        ):
            result = await PreActionVerifier().verify("http_post", {"url": "x"}, "reason")

        assert result.verdict == VerifierVerdict.SKIP
        assert result.degradation is VerifierDegradation.NO_PROVIDER

    @pytest.mark.asyncio
    async def test_an_unreadable_reply_blocks_a_network_mutation(self):
        """The exact case the 0.5 default used to let through."""
        provider = MagicMock()
        provider.provider_name = "fake"
        provider.chat_completion = AsyncMock(return_value=MagicMock(content="¯\\_(ツ)_/¯", model="m"))

        with (
            patch.object(guard, "_select_verifier_provider", AsyncMock(return_value=provider)),
            patch.object(guard, "VERIFIER_ENABLED", True),
        ):
            result = await PreActionVerifier().verify("http_post", {"url": "x"}, "reason")

        assert result.verdict == VerifierVerdict.BLOCK
        assert result.degradation is VerifierDegradation.UNPARSEABLE
