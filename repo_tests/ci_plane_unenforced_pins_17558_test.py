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
        """`langchain` requires `langgraph<1.3.0` where production says `<2.0.0`.

        The requirer is declared in the CI plane here because the real one is:
        `requirements-ci` pins `langchain==1.4.2`, so the cap it states cannot
        move. An earlier version of this fixture left `dragger` out of every
        plane, which quietly assumed the half the test below now states.
        """
        ci = {"dragger": "dragger==1.0.0"}
        assert hook.unenforced_pairs(_PROD, ci, _closure(("dragger", "widget<2.0,>=1.0"))) == []

    def test_a_cap_stated_by_a_floating_requirer_is_not_structural(self):
        """#17558 AC2's missing half, and the reason `opentelemetry-proto` was silent.

        Same capping requirement as the test above; the only difference is that
        nothing holds `dragger` at a version. `dragger==1.0.0` says `widget<2.0`,
        `dragger==2.0.0` will say whatever it likes, and CI takes the newest
        `dragger` -- so the cap travels with it and bounds nothing.
        """
        [pair] = hook.unenforced_pairs(_PROD, {}, _closure(("dragger", "widget<2.0,>=1.0")))
        assert pair.name == "widget"

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


class TestMarkersAreNotMistakenForSpecifiers:
    """#17610 review: both halves of a requirement string were being scanned."""

    def test_a_marker_comparison_does_not_look_like_an_upper_bound(self):
        """`python_version < "3.10"` is not a cap on the package."""
        assert hook.specifier_of('widget>=1.0; python_version < "3.10"') == ">=1.0"
        assert not hook.bounds_above(hook.specifier_of('widget>=1.0; python_version < "3.10"'))

    def test_a_real_cap_beside_a_marker_is_still_seen(self):
        """Contrast pair: the specifier still decides, marker or not."""
        assert hook.bounds_above(hook.specifier_of('widget<2.0,>=1.0; python_version >= "3.9"'))

    def test_an_unparseable_requirement_does_not_invent_a_bound(self):
        """Under-claim rather than fabricate: drop the marker, never scan it."""
        assert ";" not in hook.specifier_of("widget>=1.0; not a valid marker <3")

    @pytest.mark.parametrize("req", ['widget>=1; extra == "dev"', 'widget>=1; extra=="dev"'])
    def test_an_optional_requirement_is_dropped_whatever_its_spacing(self, req):
        """`extra=="x"` without spaces defeated the old substring check."""
        assert hook.is_optional(req)

    def test_a_plain_requirement_is_kept(self):
        assert not hook.is_optional("widget>=1.0")
        assert not hook.is_optional('widget>=1.0; python_version >= "3.9"')


class TestRevertingTheFixReproducesIt:
    """#17558 Gap 2 AC2 -- the worked example, with #17502 taken back out.

    `test_the_known_fix_is_not_reported` above is the INVERSE assertion, and on
    its own it is satisfied by a check that reports nothing ever. It says the
    guard is quiet while the fix is in place; it cannot say the guard would have
    spoken without it. This class supplies the other half, which is the one
    `MEASUREMENT_DISCIPLINE.md` calls the known positive: assert a case whose
    answer is already known before any clean result means anything.

    WHAT IS REAL AND WHAT IS DATA. The two plane dictionaries are read from the
    actual requirement files, so the revert is a revert of the shipped #17502 fix
    rather than of a mock. The dependency closure is stated as data because it
    comes from installed distribution metadata, and a test that read this
    machine's site-packages would pass or fail for reasons about the machine --
    the defect the parent issue is about. Every line of `_CHROMADB_CLOSURE` was
    copied from `importlib.metadata` on an interpreter with the CI plane
    installed, and `test_the_recorded_closure_still_matches_the_declared_plane`
    keeps it from rotting unnoticed.
    """

    #: The four packages #17502 added to `requirements-ci/storage.txt`. Reverting
    #: the fix means removing exactly these from the CI plane.
    FOUR = (
        "opentelemetry-api",
        "opentelemetry-sdk",
        "opentelemetry-exporter-otlp-proto-grpc",
        "opentelemetry-proto",
    )

    #: `{package: [(requirer, requirement)]}` as `chromadb==1.5.9` and its own
    #: dependencies declare it. `chromadb` is the CI-plane root that drags the
    #: OpenTelemetry stack in; `mcp` is a second unbounded requirer of the api
    #: package, recorded because a first-requirer-only reading is the mistake
    #: `ci_transitive_closure`'s docstring warns about.
    _CHROMADB_CLOSURE = {
        "opentelemetry-api": [
            ("chromadb", "opentelemetry-api>=1.2.0"),
            ("mcp", "opentelemetry-api>=1.28.0"),
            ("opentelemetry-sdk", "opentelemetry-api==1.44.0"),
            ("opentelemetry-semantic-conventions", "opentelemetry-api==1.44.0"),
            ("opentelemetry-exporter-otlp-proto-grpc", "opentelemetry-api~=1.15"),
        ],
        "opentelemetry-sdk": [
            ("chromadb", "opentelemetry-sdk>=1.2.0"),
            ("opentelemetry-exporter-otlp-proto-grpc", "opentelemetry-sdk~=1.44.0"),
        ],
        "opentelemetry-exporter-otlp-proto-grpc": [
            ("chromadb", "opentelemetry-exporter-otlp-proto-grpc>=1.2.0"),
        ],
        # Both requirers state `==1.44.0`, which reads as a cap. Neither requirer
        # is held once the pin is reverted, so the cap moves with them -- this is
        # the entry that `floating_packages` exists for.
        "opentelemetry-proto": [
            ("opentelemetry-exporter-otlp-proto-grpc", "opentelemetry-proto==1.44.0"),
            ("opentelemetry-exporter-otlp-proto-common", "opentelemetry-proto==1.44.0"),
        ],
        "opentelemetry-exporter-otlp-proto-common": [
            ("opentelemetry-exporter-otlp-proto-grpc", "opentelemetry-exporter-otlp-proto-common==1.44.0"),
        ],
        "opentelemetry-semantic-conventions": [
            ("opentelemetry-sdk", "opentelemetry-semantic-conventions==0.65b0"),
        ],
    }

    def _planes(self):
        return hook.production_requirement_names(), hook.ci_requirement_names()

    def test_the_fix_being_reverted_is_actually_in_the_tree(self):
        """Non-vacuity: a revert of nothing would report nothing and look like a pass."""
        _, ci = self._planes()
        missing = [name for name in self.FOUR if name not in ci]
        assert not missing, (
            f"{missing} are not declared in the CI plane, so this fixture is not reverting "
            "#17502 -- it is reverting something that is no longer there. Re-derive the list "
            "from requirements-ci/storage.txt before trusting anything below."
        )

    def test_production_still_pins_all_four_above(self):
        """The other half of the pair: no production upper bound, no finding either way."""
        production, _ = self._planes()
        assert all(hook.bounds_above(production[name]) for name in self.FOUR), {
            name: production.get(name) for name in self.FOUR
        }

    def test_all_four_are_reported_once_the_pin_is_reverted(self):
        """#17557's shape, reproduced. This is the assertion the issue asks for."""
        production, ci = self._planes()
        reverted = {name: spec for name, spec in ci.items() if name not in self.FOUR}
        pairs = hook.unenforced_pairs(production, reverted, self._CHROMADB_CLOSURE)
        assert sorted(pair.name for pair in pairs) == sorted(self.FOUR)

    def test_restoring_the_pin_silences_every_one_of_them(self):
        """The contrast pair, on the same closure -- only the CI declarations differ."""
        production, ci = self._planes()
        pairs = hook.unenforced_pairs(production, ci, self._CHROMADB_CLOSURE)
        assert [pair.name for pair in pairs if pair.name.startswith("opentelemetry")] == []

    def test_the_report_names_which_plane_declares_and_which_merely_installs(self):
        """AC4: the fix differs by direction, so the finding must state the direction."""
        production, ci = self._planes()
        reverted = {name: spec for name, spec in ci.items() if name not in self.FOUR}
        pairs = hook.unenforced_pairs(production, reverted, self._CHROMADB_CLOSURE)
        [grpc] = [pair for pair in pairs if pair.name == "opentelemetry-exporter-otlp-proto-grpc"]
        described = grpc.describe()
        assert "production says" in described and "CI never declares it" in described
        assert "chromadb" in described, "the requirer that installs it must be named"

    def test_the_recorded_closure_still_matches_the_declared_plane(self):
        """Guards the one input that is data rather than a file read.

        `chromadb` must still be the CI-plane root this closure hangs off. If it
        is dropped or replaced, the recorded metadata describes a plane that no
        longer exists and every assertion above becomes a statement about history.
        """
        _, ci = self._planes()
        assert "chromadb" in ci, "the recorded closure is rooted in chromadb, which the CI plane no longer declares"
        requirers = {who for entries in self._CHROMADB_CLOSURE.values() for who, _ in entries}
        assert "chromadb" in requirers


class TestFloatingPackages:
    """The rule `opentelemetry-proto` needed, stated without any file or environment."""

    def test_a_package_the_ci_plane_pins_is_held(self):
        assert hook.floating_packages({"widget": "widget==1.4.0"}, _closure(("d", "widget>=1.0"))) == set()

    def test_an_unbounded_requirer_makes_it_float(self):
        assert hook.floating_packages({}, _closure(("d", "widget>=1.0"))) == {"widget"}

    def test_a_cap_from_a_held_requirer_holds_it(self):
        ci = {"dragger": "dragger==1.0.0"}
        assert hook.floating_packages(ci, _closure(("dragger", "widget<2.0"))) == set()

    def test_floating_is_transitive(self):
        """grpc floats, so the `proto==1.44.0` it states floats too."""
        closure = {
            "grpc": [("chromadb", "grpc>=1.2.0")],
            "proto": [("grpc", "proto==1.44.0")],
        }
        assert hook.floating_packages({"chromadb": "chromadb==1.5.9"}, closure) == {"grpc", "proto"}

    def test_holding_the_intermediate_holds_the_leaf(self):
        """Contrast pair for the test above -- one declaration changes both verdicts."""
        closure = {
            "grpc": [("chromadb", "grpc>=1.2.0")],
            "proto": [("grpc", "proto==1.44.0")],
        }
        ci = {"chromadb": "chromadb==1.5.9", "grpc": "grpc==1.44.0"}
        assert hook.floating_packages(ci, closure) == set()
