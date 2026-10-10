# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one graph blend (#18141)."""

from autobot_shared.graph_retrieval import GRAPH_WEIGHT_DEFAULT, blend_graph_score


def test_matches_the_formula_graph_rag_used_before() -> None:
    base, strength = 0.8, 0.6
    assert blend_graph_score(base, base * strength, GRAPH_WEIGHT_DEFAULT) == (
        (1.0 - GRAPH_WEIGHT_DEFAULT) * base + GRAPH_WEIGHT_DEFAULT * (base * strength)
    )


def test_a_candidate_the_graph_ignores_keeps_its_score_exactly() -> None:
    for w in (0.0, 0.3, 0.7, 1.0):
        assert blend_graph_score(0.1 + 0.2, 0.1 + 0.2, w) == 0.1 + 0.2


def test_weight_zero_is_the_base_and_weight_one_is_the_signal() -> None:
    assert blend_graph_score(0.5, 0.9, 0.0) == 0.5
    assert blend_graph_score(0.5, 0.9, 1.0) == 0.9
