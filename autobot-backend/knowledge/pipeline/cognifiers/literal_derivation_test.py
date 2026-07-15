# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11017 — extractor prompt fragments + validation are derived from their model
Literal types, so allowed values can never drift from the type."""

from typing import get_args


def test_causal_effect_types_derived_from_literal():
    from knowledge.pipeline.cognifiers import causal_relationship_extractor as c
    from knowledge.pipeline.models.causal_edge import EffectType

    expected = set(get_args(EffectType))
    assert set(c._EFFECT_TYPES) == expected
    for value in expected:
        assert value in c.CAUSAL_EXTRACTION_PROMPT
        assert value in c.CAUSAL_EXTRACTION_BATCH_PROMPT


def test_event_types_derived_from_literals():
    from knowledge.pipeline.cognifiers import event_extractor as e
    from knowledge.pipeline.models.event import EventType, TemporalType

    for value in get_args(TemporalType):
        assert value in e.EVENT_EXTRACTION_PROMPT
        assert value in e.EVENT_EXTRACTION_BATCH_PROMPT
    for value in get_args(EventType):
        assert value in e.EVENT_EXTRACTION_PROMPT
        assert value in e.EVENT_EXTRACTION_BATCH_PROMPT


def test_no_sentinel_placeholders_leak_into_prompts():
    from knowledge.pipeline.cognifiers import causal_relationship_extractor as c
    from knowledge.pipeline.cognifiers import event_extractor as e
    from knowledge.pipeline.cognifiers import fact_extractor as f

    for prompt in (
        f.FACT_EXTRACTION_PROMPT,
        f.FACT_EXTRACTION_BATCH_PROMPT,
        c.CAUSAL_EXTRACTION_PROMPT,
        c.CAUSAL_EXTRACTION_BATCH_PROMPT,
        e.EVENT_EXTRACTION_PROMPT,
        e.EVENT_EXTRACTION_BATCH_PROMPT,
    ):
        assert "%%" not in prompt
