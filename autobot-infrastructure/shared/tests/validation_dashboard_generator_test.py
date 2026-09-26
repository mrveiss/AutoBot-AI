# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for validation_dashboard_generator's HTML fragments (#15585).

``_generate_phase_html``, ``_generate_alerts_html`` and
``_generate_recommendations_html`` built their fragments from triple-quoted
strings containing ``{}`` placeholders with no ``f`` prefix, so every
placeholder rendered as literal text. This dashboard is served live at
``/api/validation_dashboard/...`` (see ``autobot-backend/api/validation_dashboard.py``),
so the broken HTML reached operators without any error -- the exact
"monitoring dashboard rendering literal {status_class} to operators" shape
#14505 named. Asserting the ``f`` prefix is present would not catch this
class of bug -- this asserts the rendered fragment contains real values from
the fixture data and contains no leftover ``{identifier`` placeholder shape.
"""

import re
import sys
from pathlib import Path

# Lives here, not beside the script it tests -- see microservice_architecture_evaluator_test.py
# in this same directory for the ci.yml path-list reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from validation_dashboard_generator import ValidationDashboardGenerator  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


def _bare_generator() -> ValidationDashboardGenerator:
    """A generator with none of __init__'s heavy dependencies constructed.

    None of the three HTML-fragment methods under test read `self`, so
    skipping __init__ (which stands up a PhaseValidator, state tracker and
    progression manager) keeps this test to the unit it actually exercises.
    """
    return object.__new__(ValidationDashboardGenerator)


def test_phase_html_renders_real_values_not_placeholders():
    generator = _bare_generator()
    phase_details = [
        {
            "status_color": "#4CAF50",
            "display_name": "Foundation Phase",
            "requirements_met": 8,
            "total_requirements": 10,
            "completion_percentage": 80.0,
        }
    ]

    html = generator._generate_phase_html(phase_details)

    assert not _LEFTOVER_PLACEHOLDER_RE.search(html), (
        "Phase HTML contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert 'style="border-color: #4CAF50"' in html
    assert "<strong>Foundation Phase</strong>" in html
    assert "8/10 requirements met" in html
    assert "<strong>80.0%</strong>" in html
    assert "width: 80.0%;" in html
    assert "background: #4CAF50;" in html


def test_alerts_html_renders_real_values_not_placeholders():
    generator = _bare_generator()
    alerts = [{"level": "critical", "title": "Redis DB 3 unreachable", "message": "Connection refused"}]

    html = generator._generate_alerts_html(alerts)

    assert not _LEFTOVER_PLACEHOLDER_RE.search(html), (
        "Alerts HTML contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert 'class="alert alert-critical"' in html
    assert "Redis DB 3 unreachable" in html
    assert "Connection refused" in html


def test_recommendations_html_renders_real_values_not_placeholders():
    generator = _bare_generator()
    recommendations = [
        {
            "title": "Increase connection pool size",
            "urgency": "high",
            "description": "Pool exhaustion observed under load.",
            "action": "Raise REDIS_POOL_MAX_CONNECTIONS.",
        }
    ]

    html = generator._generate_recommendations_html(recommendations)

    assert not _LEFTOVER_PLACEHOLDER_RE.search(html), (
        "Recommendations HTML contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert "Increase connection pool size" in html
    assert 'class="recommendation-urgency urgency-high">HIGH</span>' in html
    assert "Pool exhaustion observed under load." in html
    assert "Raise REDIS_POOL_MAX_CONNECTIONS." in html


def test_phase_html_renders_not_scored_when_a_phase_publishes_no_figure():
    """#17089: a phase deferring to dedicated gates has no percentage.

    The report omits `completion_percentage` entirely when a check group was
    skipped, and omits any figure for a phase whose verdict comes from other
    workflows. Rendering 0.0% there would say "measured and found empty" -- the
    exact confusion #17089 removed from the report, reintroduced in the HTML.
    """
    generator = _bare_generator()
    phase_details = [
        {
            "status_color": "#9E9E9E",
            "display_name": "Enhanced UI/UX",
            "requirements_met": 0,
            "total_requirements": 0,
            "completion_percentage": None,
        }
    ]

    html = generator._generate_phase_html(phase_details)

    assert not _LEFTOVER_PLACEHOLDER_RE.search(html), "un-substituted placeholder in the not-scored path"
    assert "<strong>not scored</strong>" in html
    assert "width: 0.0%;" in html
    assert "0.0%</strong>" not in html, "a phase with no figure must not render as 0.0%"


def test_phase_html_still_renders_a_figure_when_one_exists():
    """The control: without it, a renderer that printed 'not scored' for every
    phase would satisfy the test above."""
    generator = _bare_generator()

    html = generator._generate_phase_html(
        [
            {
                "status_color": "#4CAF50",
                "display_name": "Core Infrastructure",
                "requirements_met": 9,
                "total_requirements": 9,
                "completion_percentage": 100.0,
            }
        ]
    )

    assert "<strong>100.0%</strong>" in html
    assert "not scored" not in html
