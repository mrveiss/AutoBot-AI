# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17558 item 2/4 — the rule is tested without an installed environment.

`unenforced_pairs` takes the dependency closure as an argument precisely so
these cases can be stated as data. A test that read the real environment would
pass or fail for reasons about this machine, which is the defect the parent
issue is about.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "lint"))

import check_ci_plane_unenforced_pins as hook  # noqa: E402

_PROD = {"widget": "widget==1.4.0"}


def _closure(*requirers):
    return {"widget": list(requirers)}


class TestWhatCountsAsUnenforced:
    def test_an_unbounded_requirer_and_no_ci_declaration_is_the_defect(self):
        """#17557's shape: the production cap has nothing keeping it."""
        [pair] = hook.unenforced_pairs(_PROD, {}, _closure(("dragger", "widget>=1.0.0")))
        assert pair.name == "widget"
        assert "dragger" in pair.describe()

    def test_declaring_it_in_the_ci_plane_silences_the_check(self):
        """The free contrast pair: this is exactly what #17502 did for OpenTelemetry."""
        ci = {"widget": "widget==1.4.0"}
        assert hook.unenforced_pairs(_PROD, ci, _closure(("dragger", "widget>=1.0.0"))) == []

    def test_a_requirer_that_caps_it_makes_the_agreement_structural(self):
        """`langchain` requires `langgraph<1.3.0` where production says `<2.0.0`."""
        assert hook.unenforced_pairs(_PROD, {}, _closure(("dragger", "widget<2.0,>=1.0"))) == []

    def test_one_unbounded_requirer_among_several_still_counts(self):
        """The case a first-requirer-only sweep missed: protobuf via onnxruntime."""
        pairs = hook.unenforced_pairs(
            _PROD,
            {},
            _closure(("capped", "widget<2.0,>=1.0"), ("uncapped", "widget>=0.9")),
        )
        assert [pair.name for pair in pairs] == ["widget"]

    def test_a_bare_floor_in_production_is_not_a_finding(self):
        """Newest satisfies `>=`, so an unbounded CI resolve cannot violate it."""
        assert hook.unenforced_pairs({"widget": "widget>=1.4.0"}, {}, _closure(("d", "widget>=1.0"))) == []

    def test_a_package_the_ci_plane_never_reaches_is_not_a_finding(self):
        """Production may declare things CI neither installs nor needs."""
        assert hook.unenforced_pairs(_PROD, {}, {}) == []


class TestBoundsAbove:
    @pytest.mark.parametrize("spec", ["==1.0", "<2.0", "<=2.0", "~=1.4", "<8.0,>=5.0"])
    def test_an_upper_bound_is_recognised(self, spec):
        assert hook.bounds_above(spec)

    @pytest.mark.parametrize("spec", [">=1.0", ">1.0", "", "!=1.2"])
    def test_no_upper_bound(self, spec):
        assert not hook.bounds_above(spec)


class TestTheClosureFollowsRequirements:
    def test_it_reaches_transitively_and_records_every_requirer(self):
        requires = {"top": ["mid>=1"], "mid": ["leaf>=2"], "other": ["leaf>=3"]}
        closure = hook.ci_transitive_closure({"top", "other"}, requires)
        assert set(closure) == {"mid", "leaf"}
        assert sorted(who for who, _ in closure["leaf"]) == ["mid", "other"], "every requirer, not just the first"


class TestTheBaselineOnlyShrinks:
    def test_every_entry_is_still_a_live_pair(self):
        """The bidirectional contract: a stale entry exempts nothing and must fail."""
        problems, notes, pairs = hook.audit()
        stranded = [problem for problem in problems if "no longer an unenforced pair" in problem]
        assert not stranded, stranded
        assert set(hook.BASELINE) <= {pair.name for pair in pairs} | {
            note.split()[2] for note in notes
        }, "every baseline entry is either a live pair or explicitly not evaluated"

    def test_the_tree_currently_has_no_unbaselined_pair(self):
        problems, _, _ = hook.audit()
        assert not problems, problems

    def test_the_known_fix_is_not_reported(self):
        """OpenTelemetry was #17557 and is declared in both planes since #17502."""
        _, _, pairs = hook.audit()
        assert not [pair for pair in pairs if pair.name.startswith("opentelemetry")]
