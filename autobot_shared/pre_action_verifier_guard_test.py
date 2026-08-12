# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the pre-action verifier decision surface (#10547, extracted #14031).

The verifier's LLM call cannot be made pure — this covers what CAN be: action-
class threshold resolution, response parsing, and verdict determination
(single-shot and panel). The ``HARD_BLOCK`` verdict semantics are the part the
extraction must preserve exactly, so ``determine_verdict``/``panel_decision``
get the most direct coverage.
"""

import os
from unittest.mock import patch

import pytest

from autobot_shared.pre_action_verifier_guard import (
    THRESHOLD_DEFAULT,
    THRESHOLD_DEPLOY,
    THRESHOLD_EXEC,
    THRESHOLD_MUTATE,
    THRESHOLD_NETWORK,
    VerifierVerdict,
    determine_verdict,
    panel_decision,
    parse_probability,
    parse_rationale,
    pre_action_verifier_enabled,
    threshold_for_tool,
)

# --------------------------------------------------------------- thresholds


def test_deploy_tools_map_to_the_deploy_threshold():
    for name in ("deploy", "ansible", "kubectl", "helm", "terraform"):
        assert threshold_for_tool(name) == THRESHOLD_DEPLOY


def test_mutate_tools_map_to_the_mutate_threshold():
    for name in ("write_file", "edit_file", "delete_file", "git_push", "git_commit"):
        assert threshold_for_tool(name) == THRESHOLD_MUTATE


def test_network_tools_map_to_the_network_threshold():
    for name in ("http_post", "http_put", "http_patch", "http_delete", "send_request"):
        assert threshold_for_tool(name) == THRESHOLD_NETWORK


def test_exec_tools_map_to_the_exec_threshold():
    for name in ("bash", "shell", "execute_command", "code_interpreter"):
        assert threshold_for_tool(name) == THRESHOLD_EXEC


def test_unknown_tool_falls_back_to_the_default_threshold():
    assert threshold_for_tool("some_exotic_tool") == THRESHOLD_DEFAULT


def test_prefix_matching_still_maps_a_deploy_variant():
    assert threshold_for_tool("ansible_playbook") == THRESHOLD_DEPLOY


# ------------------------------------------------------ verdict determination
# This is the surface the HARD_BLOCK semantics depend on — it must preserve
# the original ">=" rule exactly.


def test_probability_at_or_above_threshold_blocks():
    assert determine_verdict(0.5, 0.5) == VerifierVerdict.BLOCK
    assert determine_verdict(0.9, 0.5) == VerifierVerdict.BLOCK


def test_probability_below_threshold_passes():
    assert determine_verdict(0.49, 0.5) == VerifierVerdict.PASS
    assert determine_verdict(0.0, 0.5) == VerifierVerdict.PASS


def test_panel_blocks_once_quorum_of_refutations_is_reached():
    verdict, refutations = panel_decision([0.9, 0.9, 0.1], threshold=0.5, quorum=2)

    assert verdict == VerifierVerdict.BLOCK
    assert refutations == 2


def test_panel_passes_below_quorum():
    verdict, refutations = panel_decision([0.9, 0.1, 0.1], threshold=0.5, quorum=2)

    assert verdict == VerifierVerdict.PASS
    assert refutations == 1


def test_panel_decision_on_empty_probabilities_never_blocks():
    verdict, refutations = panel_decision([], threshold=0.5, quorum=1)

    assert verdict == VerifierVerdict.PASS
    assert refutations == 0


# ------------------------------------------------------------------- parsing


def test_parse_probability_reads_the_structured_line():
    raw = "REFUTATION_PROBABILITY: 0.85\nFLAW: x\nRATIONALE: y"
    assert parse_probability(raw) == pytest.approx(0.85)


def test_parse_probability_clamps_to_the_unit_interval():
    assert parse_probability("REFUTATION_PROBABILITY: 1.5") == pytest.approx(1.0)
    assert parse_probability("REFUTATION_PROBABILITY: -0.2") == pytest.approx(0.0)


def test_parse_probability_defaults_conservatively_on_malformed_input():
    assert parse_probability("nothing here") == pytest.approx(0.5)


def test_parse_rationale_extracts_the_labeled_text():
    raw = "REFUTATION_PROBABILITY: 0.9\nFLAW: bad\nRATIONALE: the path does not exist."
    assert "path does not exist" in parse_rationale(raw)


def test_parse_rationale_falls_back_to_raw_text_when_unlabeled():
    result = parse_rationale("no structured output at all")
    assert len(result) > 0


# ---------------------------------------------------- enable/disable config


def test_pre_action_verifier_enabled_defaults_true():
    """agent_loop/types.py:266 — the dataclass default the standard profile reproduces."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AUTOBOT_GUARD_PROFILE", None)
        os.environ.pop("AUTOBOT_GUARD_VERIFIER", None)
        assert pre_action_verifier_enabled() is True


def test_minimal_profile_disables_the_verifier():
    with patch.dict(os.environ, {"AUTOBOT_GUARD_PROFILE": "minimal"}, clear=False):
        os.environ.pop("AUTOBOT_GUARD_VERIFIER", None)
        assert pre_action_verifier_enabled() is False


def test_per_guard_env_override_wins_over_the_profile():
    with patch.dict(
        os.environ,
        {"AUTOBOT_GUARD_PROFILE": "minimal", "AUTOBOT_GUARD_VERIFIER": "1"},
        clear=False,
    ):
        assert pre_action_verifier_enabled() is True
