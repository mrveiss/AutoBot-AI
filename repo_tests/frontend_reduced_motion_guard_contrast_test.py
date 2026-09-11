# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The contrast half of the reduced-motion primitive guard (#15749).

``frontend_reduced_motion_guard_test.py`` runs the detector over the live tree,
which is green -- and a detector shown only a green tree has proved nothing; it
could return an empty list unconditionally and that test would still pass. This
file feeds it each primitive unwired (must trip, named for its kind), each one
wired or inert (must not), the waiver in both its forms, and -- because a
hand-written snippet proves the regex rather than the pipeline -- the real files
the guard reads, with their wiring taken out.
"""

from __future__ import annotations

import pytest
from repo_tests._paths import repo_root
from repo_tests.frontend_reduced_motion_guard_test import detect, findings

__all__: list[str] = []

_SRC = repo_root() / "autobot-frontend" / "src"


def _verdicts(text: str) -> list[tuple[str, str]]:
    return [(hit.primitive, hit.verdict) for hit in detect(text)]


@pytest.mark.parametrize(
    ("source", "primitive"),
    [
        ("cy.layout({ name: 'cose', animate: true }).run()", "animate-option"),
        ("list.scrollTo({ top: 0, behavior: 'smooth' })", "smooth-scroll"),
        ('el.scrollIntoView({ block: "nearest", behavior: "smooth" })', "smooth-scroll"),
        ("cy.animate({ zoom: 2, duration: 300 })", "animate-call"),
        ("const o = { chart: { animations: { enabled: true, speed: 800 } } }", "apex-animations"),
    ],
)
def test_an_unwired_primitive_is_a_finding_named_for_its_kind(source: str, primitive: str) -> None:
    """The #15749 shape: motion that never asked the user."""
    assert [(hit.primitive, hit.verdict) for hit in findings(source)] == [(primitive, "unwired")]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("cy.layout({ name: 'cose', animate: !isReducedMotion() }).run()", ("animate-option", "consults")),
        ("item.scrollIntoView({ behavior: preferredScrollBehavior() })", ("smooth-scroll", "consults")),
        ("cy.animate({\n  zoom: 2,\n  duration: isReducedMotion() ? 0 : 300,\n})", ("animate-call", "consults")),
        ("const o = { animations: { enabled: !prefersReducedMotion.value } }", ("apex-animations", "consults")),
        # The call form: a reader is a call, and a detector that strips brackets
        # stops seeing it -- the shape main.ts's global default uses.
        ("Apex = { chart: { animations: { enabled: !isReducedMotion() } } }", ("apex-animations", "consults")),
        ("cy.layout({ animate: false })", ("animate-option", "inert")),
        ("list.scrollTo({ top: 0, behavior: 'auto' })", ("smooth-scroll", "inert")),
    ],
)
def test_a_primitive_that_consults_the_preference_or_animates_nothing_is_seen_and_passes(
    source: str, expected: tuple[str, str]
) -> None:
    """Seen AND passed -- an empty result alone cannot tell passed from missed."""
    assert _verdicts(source) == [expected]


def test_nested_enabled_flags_do_not_decide_an_apexcharts_block() -> None:
    """``animateGradually.enabled`` only matters once the top-level flag is on."""
    source = "animations: {\n  easing: 'easeinout',\n  animateGradually: { enabled: true, delay: 50 },\n}"
    assert _verdicts(source) == [("apex-animations", "inert")]


def test_a_reasoned_waiver_exempts_the_line_below_it() -> None:
    source = "// reduced-motion-exempt: a one-off intro the user starts by pressing play\ncy.animate({ zoom: 2 })"
    assert _verdicts(source) == [("animate-call", "waived")]


def test_a_waiver_without_a_reason_is_itself_a_finding() -> None:
    source = "cy.animate({ zoom: 2 }) // reduced-motion-exempt:"
    assert [(hit.primitive, hit.verdict) for hit in findings(source)] == [("animate-call", "waiver has no reason")]


def test_a_commented_out_primitive_is_not_a_candidate() -> None:
    assert detect("  // cy.layout({ animate: true })\n  * scrollTo({ behavior: 'smooth' })") == []


def test_an_unbalanced_call_raises_instead_of_reading_as_clean() -> None:
    with pytest.raises(ValueError, match="unbalanced"):
        detect("cy.animate({ zoom: 2 ")


def test_the_real_cytoscape_options_trip_the_guard_once_unwired() -> None:
    """Mutate the file the guard actually reads, not a snippet (#15749, criterion 3)."""
    real = (_SRC / "components" / "knowledge" / "KnowledgeGraph.vue").read_text(encoding="utf-8")
    wired = real.count("animate: !isReducedMotion()")
    assert wired >= 1, "KnowledgeGraph.vue no longer carries the wired option this test mutates"
    assert findings(real) == []
    unwired = real.replace("animate: !isReducedMotion()", "animate: true")
    assert [hit.primitive for hit in findings(unwired)] == ["animate-option"] * wired


def test_the_real_tween_trips_the_guard_once_its_duration_ignores_the_preference() -> None:
    real = (_SRC / "components" / "knowledge" / "KnowledgeGraph.vue").read_text(encoding="utf-8")
    assert "isReducedMotion() ? 0 : 300" in real, "the tween this test mutates has moved"
    unwired = real.replace("isReducedMotion() ? 0 : 300", "300")
    assert [hit.primitive for hit in findings(unwired)] == ["animate-call"]


def test_the_real_chart_base_trips_the_guard_if_its_theme_turns_animation_on() -> None:
    real = (_SRC / "components" / "charts" / "BaseChart.vue").read_text(encoding="utf-8")
    anchor = "    animations: {\n      easing: 'easeinout',"
    assert anchor in real, "BaseChart.vue's theme animations block has moved"
    assert findings(real) == []
    unwired = real.replace(anchor, "    animations: {\n      enabled: true,\n      easing: 'easeinout',")
    assert [hit.primitive for hit in findings(unwired)] == ["apex-animations"]
