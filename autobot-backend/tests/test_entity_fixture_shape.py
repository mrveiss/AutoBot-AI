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


def _real_entity_doc() -> Dict[str, Any]:
    """A genuine entity document, from the builder itself.

    Derived, never hardcoded: a hardcoded copy would drift the same way the
    fixtures did.

    ``self`` is None deliberately. ``_build_entity_document``
    (``autobot_memory_graph/entities.py:68``) is annotated as a method but
    touches no attribute. If someone adds one, this raises ``AttributeError:
    'NoneType'`` naming the exact access — loud, and at the right line. A
    ``MagicMock()`` would instead succeed silently and bake a mock into a field
    value, which is the same class of lie these tests exist to catch.
    """
    from autobot_memory_graph.entities import EntityOperationsMixin

    return EntityOperationsMixin._build_entity_document(
        None,
        entity_id="e1",
        entity_type="service",
        name="Redis",
        observations=["an observation"],
        entity_metadata={},
    )


def _real_entity_keys() -> Set[str]:
    return set(_real_entity_doc().keys())


def _assert_is_entity_document(fixture: Dict[str, Any]) -> None:
    """Fail unless *fixture* is shaped like something the graph would store.

    Whole-document equality, not a subset: a partial fixture passes a subset
    check and still renders nothing, which reads as a layer bug rather than a
    fixture bug. Types are compared field-by-field against the real document
    because ``observations`` being a str instead of a list is silent — a later
    ``join`` over it yields characters.
    """
    real = _real_entity_doc()

    assert set(fixture) == set(real), (
        f"not an entity document — missing {sorted(set(real) - set(fixture))}, "
        f"invented {sorted(set(fixture) - set(real))}"
    )
    for key, value in fixture.items():
        assert isinstance(value, type(real[key])), f"{key}: expected {type(real[key]).__name__}, got {type(value).__name__}"
    assert fixture["observations"], "an entity with no observations renders nothing"
    assert fixture["name"], "L2 requires a name to render a line"


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

        assert ENTITY_FACTS, "the harness needs at least one entity to exercise L2"
        for fact in ENTITY_FACTS:
            _assert_is_entity_document(fact)

    def test_a_subset_of_the_right_keys_is_not_enough(self):
        """Guards the guard.

        A key-subset check passes for `{"observations": "a string"}` and for
        `{"observations": []}` — both of which render nothing, and the second of
        which would send someone chasing a phantom L2 bug. Whole-document
        equality plus per-field types is what actually constrains a fixture.
        """
        real = _real_entity_doc()

        with pytest.raises(AssertionError):
            _assert_is_entity_document({"observations": ["x"]})  # incomplete
        with pytest.raises(AssertionError):
            _assert_is_entity_document({**real, "observations": "not a list"})  # wrong type


class TestTheLayerReadsAFieldThatExists:
    """Guards the fix itself, not just the fixtures.

    ``strict=True`` is the point. A conditional ``pytest.xfail()`` would go
    quietly green when #13686 lands and then silently re-arm — any later
    regression that empties L2 would read as an expected failure, which is the
    "green tick means nothing" property this whole change exists to remove.
    Strict makes the fix XPASS, which *fails*, forcing the marker's removal in
    the PR that does the fixing.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="#13686: L2 reads description/content; entity documents carry observations",
    )
    @pytest.mark.asyncio
    async def test_l2_renders_from_a_document_the_graph_would_store(self):
        from unittest.mock import AsyncMock

        from chat_history.layers import Layer2OnDemand

        doc = _real_entity_doc()
        doc["observations"] = ["in-memory store backing session state"]
        graph = AsyncMock()
        graph.search_entities = AsyncMock(return_value=[doc])

        rendered = await Layer2OnDemand().render({"user_message": "How is Redis configured?", "memory_graph": graph})

        assert "Redis" in rendered
        assert "in-memory store" in rendered
