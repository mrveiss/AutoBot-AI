# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``combine_enforcement_modes`` pins the precedence decision for #15086.

`get_endpoint_enforcement` (`services/feature_flags.py`) had exactly one caller
before this issue: its own definition. An operator could write a per-endpoint
override, see it accepted and audit-logged, read it back -- and it never
reached an authorization decision.

The precedence chosen here: the **stricter** side wins. A per-endpoint
override may tighten enforcement above the global mode; it may never loosen it
below. Allowing a per-endpoint override to relax below the global mode would be
a per-endpoint fail-open -- the same class of defect as #14010 and #14866,
just with a narrower blast radius.
"""

from __future__ import annotations

import pytest

from services.feature_flags import EnforcementMode, combine_enforcement_modes

#: Every ordered pair of modes, used for the exhaustive precedence sweep below.
_ALL_MODE_PAIRS: tuple[tuple[EnforcementMode, EnforcementMode], ...] = tuple(
    (g, o) for g in EnforcementMode for o in EnforcementMode
)


def _stricter(a: EnforcementMode, b: EnforcementMode) -> EnforcementMode:
    """Independent re-derivation of "stricter", so the test does not just
    reimplement the function it is pinning."""
    order = [EnforcementMode.DISABLED, EnforcementMode.LOG_ONLY, EnforcementMode.ENFORCED]
    return a if order.index(a) >= order.index(b) else b


class TestNoOverrideLeavesTheGlobalModeUntouched:
    """The half that must NOT change: an endpoint with no override stored."""

    @pytest.mark.parametrize("global_mode", list(EnforcementMode))
    def test_no_override_is_the_global_mode_verbatim(self, global_mode):
        assert combine_enforcement_modes(global_mode, None) == global_mode

    def test_the_sweep_itself_is_not_empty(self):
        """Non-vacuity: a parametrize list that silently became empty must fail
        loudly, not pass by skipping every case."""
        assert list(EnforcementMode), "EnforcementMode has no members -- the sweep above tested nothing"


class TestAnOverrideCanTightenButNeverLoosen:
    """The wiring this issue exists for."""

    def test_enforced_override_wins_over_disabled_global(self):
        """The exact scenario #15086 reports: an endpoint set to enforced while
        the fleet is disabled must actually become enforced."""
        assert combine_enforcement_modes(EnforcementMode.DISABLED, EnforcementMode.ENFORCED) == EnforcementMode.ENFORCED

    def test_disabled_override_cannot_loosen_an_enforced_global(self):
        """The exact scenario #15086 reports as the opposite-direction defect:
        an endpoint "exempted" while the fleet enforces must keep enforcing."""
        assert combine_enforcement_modes(EnforcementMode.ENFORCED, EnforcementMode.DISABLED) == EnforcementMode.ENFORCED

    def test_log_only_override_cannot_loosen_an_enforced_global(self):
        assert combine_enforcement_modes(EnforcementMode.ENFORCED, EnforcementMode.LOG_ONLY) == EnforcementMode.ENFORCED

    def test_log_only_override_tightens_a_disabled_global(self):
        assert combine_enforcement_modes(EnforcementMode.DISABLED, EnforcementMode.LOG_ONLY) == EnforcementMode.LOG_ONLY


class TestTheExhaustiveSweepMatchesStricterWinsForEveryPair:
    """Every (global, override) combination independently re-derived.

    A hand-picked set of examples can pass by accident if the implementation
    is subtly wrong for a pair no one thought to write down. This sweeps the
    full 3x3 space.
    """

    @pytest.mark.parametrize("global_mode,override", _ALL_MODE_PAIRS)
    def test_matches_the_independent_stricter_of_the_two(self, global_mode, override):
        assert combine_enforcement_modes(global_mode, override) == _stricter(global_mode, override)

    def test_the_pair_sweep_is_not_empty(self):
        """Non-vacuity: nine pairs are expected; fewer means the generator broke."""
        assert len(_ALL_MODE_PAIRS) == 9, f"expected all 3x3 mode pairs, got {len(_ALL_MODE_PAIRS)}: {_ALL_MODE_PAIRS}"
