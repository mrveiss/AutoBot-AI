# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Controls for the land-next park checker's whole-expression and follower rules (#20825)."""

from __future__ import annotations

from repo_tests._gate_if import runs_when_needs_skipped, runs_without_land_next
from repo_tests.required_context_complements_test import (
    LABEL_IS_LAND_NEXT,
    LAND_NEXT,
    _fixture,
    _park_violations,
)

CANONICAL = f"${{{{ {LAND_NEXT} && (github.event.action != 'labeled' || {LABEL_IS_LAND_NEXT}) }}}}"


def test_the_canonical_condition_is_accepted_and_a_tautology_quoting_the_pieces_is_not():
    assert not runs_without_land_next(CANONICAL)
    assert runs_without_land_next(f"${{{{ true || ({LAND_NEXT} && {LABEL_IS_LAND_NEXT}) }}}}")
    assert runs_without_land_next(f"${{{{ {LAND_NEXT} || {LABEL_IS_LAND_NEXT} }}}}")


def test_a_tautology_that_quotes_both_substrings_fails_the_park_checker():
    docs = _fixture()
    docs["marker-tests.yml"]["jobs"]["marker-tests"]["if"] = f"${{{{ true || ({LAND_NEXT} && {LABEL_IS_LAND_NEXT}) }}}}"
    assert any("marker-tests.yml 'marker-tests' is not held back" in p for p in _park_violations(docs))


def test_a_follower_that_overrides_skip_propagation_is_not_held_back_but_an_ordinary_one_is():
    docs = _fixture()
    jobs = docs["marker-tests.yml"]["jobs"]
    jobs["after"] = {"needs": ["marker-tests"], "runs-on": "ubuntu-latest", "steps": []}
    assert not any("'after'" in p for p in _park_violations(docs))
    jobs["after"]["if"] = "${{ always() }}"
    assert any("marker-tests.yml 'after' is not held back" in p for p in _park_violations(docs))
    jobs["after"]["if"] = "${{ always() && needs.marker-tests.result == 'success' }}"
    assert not runs_when_needs_skipped(jobs["after"]["if"])
    assert not any("'after'" in p for p in _park_violations(docs))
