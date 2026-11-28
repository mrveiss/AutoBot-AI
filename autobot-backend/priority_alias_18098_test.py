# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Two urgency forks became aliases of the canonical `Priority` (#18098).

`KnowledgePriority` and `MaintenancePriority` were four-member enums
(critical/high/medium/low). Expected values are LITERALS captured from the old
enums, never derived from the code under test.
"""

from __future__ import annotations

import asyncio

from autobot_shared.status_enums import Priority

OLD_KNOWLEDGE_ORDER = ["critical", "high", "medium", "low"]


def test_the_two_forks_are_the_canonical_priority():
    import temporal_knowledge_manager as tkm
    from services import analytics_service

    assert tkm.KnowledgePriority is Priority
    assert analytics_service.MaintenancePriority is Priority


def test_the_pin_is_the_old_declaration_order():
    import temporal_knowledge_manager as tkm

    assert [p.value for p in tkm.KNOWLEDGE_PRIORITY_ORDER] == OLD_KNOWLEDGE_ORDER


def test_priority_distribution_is_byte_identical():
    """Old: {priority.value: 0 for priority in KnowledgePriority} -> 4 keys, this order."""
    import temporal_knowledge_manager as tkm

    manager = tkm.TemporalKnowledgeManager()
    manager.register_content("c1", {"category": "api"}, "h1")
    dist = manager._collect_distribution_stats()[1]
    assert dist == {"critical": 0, "high": 1, "medium": 0, "low": 0}
    assert list(dist) == OLD_KNOWLEDGE_ORDER


def test_expiry_jobs_keep_the_old_order():
    """Old iteration was CRITICAL, HIGH, MEDIUM, LOW; the canonical's own order is reversed."""
    import temporal_knowledge_manager as tkm

    manager = tkm.TemporalKnowledgeManager()
    for content_id, meta in (("low", {"category": "logs"}), ("crit", {"category": "x", "path": "p"})):
        manager.register_content(content_id, meta, "h")
    manager.temporal_metadata["low"].priority = Priority.LOW
    manager.temporal_metadata["crit"].priority = Priority.CRITICAL
    for entry in manager.temporal_metadata.values():
        entry.invalidation_time = 1.0
    jobs = asyncio.run(manager.scan_for_expired_content())
    assert [job.priority.value for job in jobs] == ["critical", "low"]


def test_maintenance_recommendation_wire_is_byte_identical():
    """Old to_dict emitted the lowercase value string; so does the alias."""
    from services.analytics_service import MaintenancePriority, MaintenanceRecommendation

    rec = MaintenanceRecommendation(
        id="r1",
        title="t",
        description="d",
        priority=MaintenancePriority.HIGH,
        category="c",
        affected_component="x",
        predicted_issue="p",
        confidence=0.5,
        recommended_action="a",
        estimated_impact="i",
    )
    assert rec.to_dict()["priority"] == "high"
    assert [MaintenancePriority(v).value for v in ("critical", "high", "medium", "low")] == OLD_KNOWLEDGE_ORDER
