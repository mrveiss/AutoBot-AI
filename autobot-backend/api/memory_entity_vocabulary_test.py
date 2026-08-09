#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Entity-type vocabulary contract — Issue #13795.

`EntityCreateRequest` is the body of POST /api/memory/entities, which calls
`AutoBotMemoryGraph.create_entity`. The schema used to carry its own literal
copy of the *knowledge base's* lower-case vocabulary ("decision", "bug_fix", …)
while `create_entity` validates against the memory graph's `ENTITY_TYPES`
("DECISION", "BUG", …). The two sets were **disjoint**, so every value the
schema admitted then raised ValueError one layer down:

    $ for t in research context feature conversation implementation \
               user_preference learning bug_fix decision task; do POST …; done
    research         -> 400 {"detail":"Internal server error"}
    ...              (all ten)
    task             -> 400 {"detail":"Internal server error"}

Entity creation was impossible through the API for any input at all, and the
memory graph could not be populated — which silently disabled every
graph-dependent feature (graph-RAG expansion, the #13474 connection path, the
memory.* MCP tools, the Entity Graph GUI).

This is the same defect #13452 fixed for relation types, one field over. These
tests pin the two vocabularies together so a literal copy cannot come back.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from autobot_memory_graph.core import ENTITY_TYPES  # noqa: E402
from api.schemas_knowledge import EntityCreateRequest, _VALID_ENTITY_TYPES  # noqa: E402


def _req(entity_type: str) -> EntityCreateRequest:
    return EntityCreateRequest(entity_type=entity_type, name="X", observations=["o"])


def test_schema_vocabulary_is_the_graph_vocabulary():
    """The regression itself: a literal copy is free to drift, a derivation is not."""
    assert _VALID_ENTITY_TYPES == frozenset(ENTITY_TYPES)


@pytest.mark.parametrize("entity_type", sorted(ENTITY_TYPES))
def test_every_accepted_type_is_one_create_entity_accepts(entity_type: str):
    """Whatever the schema admits must survive create_entity's own validation.

    Previously this was false for all ten admitted values.
    """
    assert _req(entity_type).entity_type in ENTITY_TYPES


@pytest.mark.parametrize("entity_type", sorted(ENTITY_TYPES))
def test_lowercase_is_normalised_not_rejected(entity_type: str):
    """Callers written against the old lower-case schema keep working, and the
    value handed to create_entity is the canonical casing it requires."""
    assert _req(entity_type.lower()).entity_type == entity_type


def test_mixed_case_is_normalised():
    assert _req("DeCiSiOn").entity_type == "DECISION"


def test_unknown_type_is_rejected():
    with pytest.raises(ValueError):
        _req("definitely_not_a_type")


def test_rejection_message_names_the_allowed_values():
    """The old message was thrown away by the router; a caller must be able to
    see what is allowed without reading the source."""
    with pytest.raises(ValueError) as exc_info:
        _req("nope")
    message = str(exc_info.value)
    assert "DECISION" in message


def test_knowledge_base_vocabulary_is_gone():
    """The literal copy admitted these and create_entity rejected all of them."""
    for stale in ("bug_fix", "user_preference", "context", "learning", "implementation"):
        with pytest.raises(ValueError):
            _req(stale)
