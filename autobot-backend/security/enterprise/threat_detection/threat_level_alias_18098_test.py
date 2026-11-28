# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18098 -- ``threat_detection.types.ThreatLevel`` is the canonical ``Severity``.

The enum used to be a four-rung fork of ``autobot_shared.status_enums.Severity``
with identical string values. These pins hold on the pre-change tree and the
aliased tree alike, so they prove the swap is wire-neutral: the names, the
values, the priority ladder, the primary-threat choice and the
``threats_by_level`` keys do not move. Only the identity assertion is
post-change, and it is the one that fails if the fork returns.
"""

from __future__ import annotations

import asyncio
import itertools
from unittest.mock import create_autospec, patch

import pytest

pytest.importorskip("sklearn", reason="scikit-learn not installed -- optional ML dep")

from autobot_shared.status_enums import Severity  # noqa: E402
from security.enterprise.threat_detection import ThreatLevel as PackageThreatLevel  # noqa: E402
from security.enterprise.threat_detection.analyzers.command_injection import (  # noqa: E402
    CommandInjectionAnalyzer,
)
from security.enterprise.threat_detection.engine import ThreatDetectionEngine  # noqa: E402
from security.enterprise.threat_detection.models import (  # noqa: E402
    AnalysisContext,
    EventHistory,
    SecurityEvent,
    ThreatEvent,
)
from security.enterprise.threat_detection.types import (  # noqa: E402
    SEVERITY_PRIORITY,
    ThreatCategory,
    ThreatLevel,
    get_max_severity,
)

VALUES = ("low", "medium", "high", "critical")


def test_members_are_exactly_the_four_rungs():
    # By name, not by iteration: the canonical enum also carries rungs the old fork
    # lacked (unknown, warning, ...), and nothing iterates ThreatLevel (#18098).
    assert [(ThreatLevel[n].name, ThreatLevel[n].value) for n in ("LOW", "MEDIUM", "HIGH", "CRITICAL")] == [
        ("LOW", "low"),
        ("MEDIUM", "medium"),
        ("HIGH", "high"),
        ("CRITICAL", "critical"),
    ]


@pytest.mark.parametrize("value", VALUES)
def test_value_round_trip_and_name(value):
    member = ThreatLevel(value)
    assert member.value == value
    assert member.name == value.upper()


def test_threat_level_is_the_canonical_severity():
    # Post-change only: pre-change this is a separate class and fails, by design.
    assert ThreatLevel is Severity
    assert PackageThreatLevel is Severity


def test_priority_ladder_pinned():
    assert {n: SEVERITY_PRIORITY[ThreatLevel[n].value] for n in ("LOW", "MEDIUM", "HIGH", "CRITICAL")} == {
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }


def test_get_max_severity_full_grid_pinned():
    expected = {
        ("low", "low"): "low",
        ("low", "medium"): "medium",
        ("low", "high"): "high",
        ("low", "critical"): "critical",
        ("medium", "low"): "medium",
        ("medium", "medium"): "medium",
        ("medium", "high"): "high",
        ("medium", "critical"): "critical",
        ("high", "low"): "high",
        ("high", "medium"): "high",
        ("high", "high"): "high",
        ("high", "critical"): "critical",
        ("critical", "low"): "critical",
        ("critical", "medium"): "critical",
        ("critical", "high"): "critical",
        ("critical", "critical"): "critical",
    }
    actual = {(a, b): get_max_severity(a, b) for a, b in itertools.product(VALUES, VALUES)}
    assert actual == expected


def _threat(level: str, confidence: float, tag: str) -> ThreatEvent:
    return ThreatEvent(
        event_id=tag,
        timestamp=None,
        threat_category=ThreatCategory.API_ABUSE,
        threat_level=ThreatLevel(level),
        confidence_score=confidence,
        user_id="u",
        source_ip="x",
        action="a",
        resource="r",
        details={},
        raw_event={},
        mitigation_actions=[],
    )


def _bare_engine() -> ThreatDetectionEngine:
    """An engine with only the state ``_process_detected_threat`` touches."""
    from collections import defaultdict

    engine = object.__new__(ThreatDetectionEngine)
    engine.stats = {
        "threats_detected": 0,
        "threats_by_category": defaultdict(int),
        "threats_by_level": defaultdict(int),
    }
    return engine


def test_primary_threat_and_level_stats_pinned():
    threats = [
        _threat("medium", 0.99, "m"),
        _threat("critical", 0.10, "c-low-conf"),
        _threat("critical", 0.80, "c-high-conf"),
        _threat("high", 0.95, "h"),
        _threat("low", 1.0, "l"),
    ]
    engine = _bare_engine()
    with patch.object(ThreatDetectionEngine, "_execute_response_actions", autospec=True) as respond:
        primary = asyncio.run(engine._process_detected_threat(threats))
    assert primary.event_id == "c-high-conf"
    assert dict(engine.stats["threats_by_level"]) == {"critical": 1}
    assert all(type(k) is str for k in engine.stats["threats_by_level"])
    assert engine.stats["threats_detected"] == 1
    respond.assert_awaited_once_with(engine, primary)


EXPECTED_INJECTION_SEVERITIES = {
    "shell_injection": "high",
    "destructive_commands": "critical",
    "network_tools": "high",
    "encoding_tools": "medium",
    "privilege_escalation": "high",
    "system_file_access": "high",
    "script_injection": "medium",
}


def test_injection_pattern_severities_pinned():
    engine = create_autospec(ThreatDetectionEngine, instance=True, spec_set=True)
    patterns = ThreatDetectionEngine._load_injection_patterns(engine)
    assert {p["category"]: p["severity"] for p in patterns} == EXPECTED_INJECTION_SEVERITIES
    for pattern in patterns:
        assert ThreatLevel(pattern["severity"]).value == pattern["severity"]


@pytest.mark.parametrize(
    ("command", "level"),
    [("ls", None), ("python -c x", "medium"), ("curl x", "high"), ("rm -rf x", "critical")],
)
def test_command_injection_analyzer_level_pinned(command, level):
    engine = create_autospec(ThreatDetectionEngine, instance=True, spec_set=True)
    context = AnalysisContext(
        config={},
        user_profiles={},
        event_history=EventHistory(events=[]),
        injection_patterns=[
            p
            for p in ThreatDetectionEngine._load_injection_patterns(engine)
            if p["category"] in {"script_injection", "network_tools", "destructive_commands"}
        ],
        file_signatures=[],
        api_patterns=[],
    )
    event = SecurityEvent(raw_event={"details": {"command": command, "args": ""}})
    threat = asyncio.run(CommandInjectionAnalyzer().analyze(event, context))
    if level is None:
        assert threat is None
    else:
        assert threat.threat_level is ThreatLevel(level)
        assert threat.threat_level.value == level
