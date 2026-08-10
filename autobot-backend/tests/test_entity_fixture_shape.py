# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Entity fixtures must match the document the graph actually stores (#13866).

The tiered-context A/B concluded "all five layers render" and that conclusion
changed a production default. It was wrong about L2, and the reason it was wrong
is the failure mode these tests exist to prevent:

    the fixture and the layer shared the same false assumption, so they agreed.

`Layer2OnDemand` read ``description``/``content``. The A/B harness and the layer's
own unit test both supplied ``{"name": ..., "description": ...}``. Every test
passed. No production write path has ever produced a ``description`` key, so the
layer returned "" on every real turn — the exact symptom #13686 was filed for and
believed fixed.

A fixture invented alongside the code it verifies certifies nothing. These tests
pin fixtures against `_build_entity_document`, the single function that defines
what an entity document is, so the next divergence fails here instead of in
production.
"""

from typing import Any, Dict, Set

import pytest


def _real_entity_keys() -> Set[str]:
    """The keys an entity document actually carries, from the builder itself.

    Derived, never hardcoded: a hardcoded copy would drift the same way the
    fixtures did.
    """
    from autobot_memory_graph.entities import EntityOperationsMixin

    doc: Dict[str, Any] = EntityOperationsMixin._build_entity_document(
        None,  # unbound: the builder is pure and does not touch self
        entity_id="e1",
        entity_type="service",
        name="Redis",
        observations=["an observation"],
        entity_metadata={},
    )
    return set(doc.keys())


class TestTheBuilderDefinesTheShape:
    def test_the_document_has_observations_and_no_description(self):
        """The precondition the A/B got wrong.

        If this ever fails, an entity really did gain a ``description`` field and
        the rest of this file should be revisited rather than deleted.
        """
        keys = _real_entity_keys()

        assert "observations" in keys, "entity text lives in observations"
        assert "description" not in keys, "no write path produces a description"
        assert "content" not in keys, "no write path produces a content key"


class TestFixturesMatchProduction:
    """Any dict claiming to be an entity document must be shaped like one."""

    def test_the_ab_harness_entity_fixture_is_a_real_document(self):
        """`scripts/tiered_context_ab.py` fed L2 an invented shape, which is how
        a layer that cannot render was measured as rendering."""
        from scripts.tiered_context_ab import ENTITY_FACTS

        real = _real_entity_keys()

        assert ENTITY_FACTS, "the harness needs at least one entity to exercise L2"
        for fact in ENTITY_FACTS:
            unknown = set(fact) - real
            assert not unknown, f"fixture invents keys production never writes: {sorted(unknown)}"
            assert "observations" in fact, "a real entity carries its text in observations"


class TestTheLayerReadsAFieldThatExists:
    """Guards the fix itself, not just the fixtures.

    #13686 is what teaches L2 to read ``observations``. Until it lands this test
    records the defect rather than asserting it away — a passing test here must
    mean the layer works, never merely that it was called.
    """

    @pytest.mark.asyncio
    async def test_l2_renders_from_a_document_the_graph_would_store(self):
        from unittest.mock import AsyncMock

        from autobot_memory_graph.entities import EntityOperationsMixin
        from chat_history.layers import Layer2OnDemand

        doc = EntityOperationsMixin._build_entity_document(
            None,
            entity_id="e1",
            entity_type="service",
            name="Redis",
            observations=["in-memory store backing session state"],
            entity_metadata={},
        )
        graph = AsyncMock()
        graph.search_entities = AsyncMock(return_value=[doc])

        rendered = await Layer2OnDemand().render({"user_message": "How is Redis configured?", "memory_graph": graph})

        if not rendered:
            pytest.xfail("#13686: L2 reads description/content, which entity documents do not carry")
        assert "Redis" in rendered
        assert "in-memory store" in rendered
