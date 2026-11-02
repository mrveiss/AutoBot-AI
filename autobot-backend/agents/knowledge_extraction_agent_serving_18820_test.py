# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent's `active_only` filter is the one serving predicate (#18820).

An inactive, expired or not-yet-valid extracted fact is dropped; an active one is kept.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agents.knowledge_extraction_agent import KnowledgeExtractionAgent
from models.atomic_fact import AtomicFact, FactType, TemporalType

_NOW = datetime.now(tz=timezone.utc)


def _fact(name: str, **overrides) -> AtomicFact:
    fields = dict(
        subject=name,
        predicate="is",
        object="x",
        fact_type=FactType.FACT,
        temporal_type=TemporalType.DYNAMIC,
        confidence=0.9,
        source="test",
        extraction_method="manual",
        valid_from=_NOW - timedelta(days=1),
    )
    fields.update(overrides)
    return AtomicFact(**fields)


def _filter(facts, **kwargs):
    agent = object.__new__(KnowledgeExtractionAgent)  # filter_facts reads no instance state
    return agent.filter_facts(facts, **kwargs)


def test_active_only_keeps_an_active_fact_and_drops_inactive_expired_and_future_ones() -> None:
    facts = [
        _fact("active"),
        _fact("inactive", is_active=False),
        _fact("expired", valid_until=_NOW - timedelta(hours=1)),
        _fact("future", valid_from=_NOW + timedelta(hours=1)),
        _fact("open", valid_until=_NOW + timedelta(hours=1)),
    ]
    assert [f.subject for f in _filter(facts)] == ["active", "open"]


def test_active_only_false_returns_every_fact() -> None:
    """Contrast: the predicate applies only when `active_only` asks for it."""
    facts = [_fact("active"), _fact("inactive", is_active=False)]
    assert [f.subject for f in _filter(facts, active_only=False)] == ["active", "inactive"]
