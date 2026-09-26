#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Drift guard for the artifact half of the entity vocabulary (Issue #17539).

`ENTITY_TYPES` declared twelve types and not one of them named an artifact:
every member was either a unit of work (BUG, FEATURE, TASK, DECISION) or a
record of something a user did (`*_ACTIVITY`, SECRET_USAGE). `FILE_ACTIVITY` is
"a file was opened", not "a file". Meanwhile `CORE_RELATION_TYPES` already
carried `implements`, `references`, `informs` and `fixes` — promoted there
because `agents.graph_entity_extractor` writes them into the graph. The verbs
existed and the nouns did not, so "this fact came from that document" and "this
task implements that function" were unsayable.

Two things make a vocabulary addition provable rather than assumed:

1. **The negative case.** A test that adds a DOCUMENT and asserts it was
   accepted proves nothing on its own — "the type was added" and "validation
   does not run" produce the same green. Every positive here is paired with an
   undeclared type asserted to be rejected.
2. **The stored document.** Acceptance is asserted against the entity handed to
   Redis, not against the absence of an exception. A double that never captures
   what was built cannot notice a builder that dropped it.

Rejection also has to be *observable*: `create_entity` wraps storage failures in
`RuntimeError("Entity creation failed")`, so validation raising inside that
`try` would reach callers as a storage error. #13452 is the precedent — a raise
every caller catches is the same defect as no raise at all.

Not covered here, deliberately:
  * #13805 owns the 17 call sites passing types `create_entity` rejects
    (`system`, `agent`, `context`, `CONCEPT`, `bug_fix`, and the case-only
    `conversation` / `task`). None of them is DOCUMENT or CODE.
  * #17540 owns the missing `CODE` intent pattern — pinned below as an absence
    so the gap stays executable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from api.schemas_knowledge import _VALID_ENTITY_TYPES, EntityCreateRequest
from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.core import ENTITY_TYPES
from autobot_memory_graph.semantic_search import (
    _ENTITY_TYPE_PATTERNS,
    MemoryGraphQueryProcessor,
)

ARTIFACT_TYPES = ("DOCUMENT", "CODE")

# Spellings a caller plausibly reaches for that the graph must still refuse.
# The lower-case pair matters most: normalisation lives in the API schema, not
# in create_entity, so the graph stays case-sensitive.
UNDECLARED_TYPES = ("DOCUMENTS", "FILE", "ARTIFACT", "SOURCE_CODE", "document", "code")


def _graph() -> tuple[AutoBotMemoryGraph, Mock]:
    """A graph whose Redis JSON ops are async but whose json() call is sync."""
    graph = AutoBotMemoryGraph()
    graph._initialized = True
    json_ops = Mock()
    json_ops.set = AsyncMock()
    graph.redis_client = Mock()
    graph.redis_client.json = Mock(return_value=json_ops)
    # No knowledge base -> no embedding generation; no real PropertyGraph.
    graph.knowledge_base = None
    property_graph = Mock()
    property_graph.add_node = AsyncMock()
    graph._property_graph = property_graph
    return graph, json_ops


class TestArtifactTypesAreDeclared:
    """The vocabulary now names artifacts, not only work and activity."""

    @pytest.mark.parametrize("entity_type", ARTIFACT_TYPES)
    def test_artifact_type_is_declared(self, entity_type: str) -> None:
        assert entity_type in ENTITY_TYPES

    def test_the_artifact_did_not_replace_the_activity(self) -> None:
        """DOCUMENT is the file; FILE_ACTIVITY is the act of touching one.

        Both must stay declared — an upload event is still a thing the graph
        records, and collapsing the two is the conflation this issue is about.
        """
        assert {"DOCUMENT", "FILE_ACTIVITY"} <= ENTITY_TYPES

    def test_no_third_spelling_of_either_artifact(self) -> None:
        """#13452 one field over: two spellings of one concept is the defect."""
        for stale in ("FILE", "SOURCE_CODE", "DOC", "SOURCE"):
            assert stale not in ENTITY_TYPES


class TestCreateEntityStoresTheType:
    """Acceptance is what reached storage, not what failed to raise."""

    @pytest.mark.parametrize("entity_type", ARTIFACT_TYPES)
    async def test_the_stored_entity_carries_the_artifact_type(self, entity_type: str) -> None:
        graph, json_ops = _graph()

        entity = await graph.create_entity(
            entity_type=entity_type,
            name="Quarterly plan",
            observations=["ingested from an upload"],
        )

        json_ops.set.assert_awaited_once()
        # _store_entity_in_redis calls json().set(key, "$", entity).
        stored = json_ops.set.await_args.args[2]
        assert stored["type"] == entity_type
        assert entity["type"] == entity_type

    @pytest.mark.parametrize("entity_type", ARTIFACT_TYPES)
    async def test_the_entity_is_keyed_as_a_memory_entity(self, entity_type: str) -> None:
        """A write that lands under no readable key is not a write."""
        graph, json_ops = _graph()

        entity = await graph.create_entity(entity_type=entity_type, name="X", observations=["o"])

        assert json_ops.set.await_args.args[0] == f"memory:entity:{entity['id']}"


class TestUndeclaredTypesAreStillRejected:
    """Without this, "the type was added" and "validation is dead" look alike."""

    @pytest.mark.parametrize("entity_type", UNDECLARED_TYPES)
    async def test_undeclared_type_raises(self, entity_type: str) -> None:
        graph, _ = _graph()

        with pytest.raises(ValueError):
            await graph.create_entity(entity_type=entity_type, name="X", observations=["o"])

    @pytest.mark.parametrize("entity_type", UNDECLARED_TYPES)
    async def test_nothing_is_written_for_a_rejected_type(self, entity_type: str) -> None:
        graph, json_ops = _graph()

        with pytest.raises(ValueError):
            await graph.create_entity(entity_type=entity_type, name="X", observations=["o"])

        json_ops.set.assert_not_awaited()

    async def test_the_rejection_is_not_folded_into_the_storage_wrapper(self) -> None:
        """create_entity turns any storage failure into RuntimeError.

        Validation therefore has to run *before* that try, or a caller that
        catches ValueError — as api/memory.py does to answer 400 (#13795) —
        sees a storage error instead and reports the wrong cause.
        """
        graph, _ = _graph()

        with pytest.raises(ValueError) as exc_info:
            await graph.create_entity(entity_type="ARTIFACT", name="X", observations=["o"])

        assert not isinstance(exc_info.value, RuntimeError)

    async def test_the_message_names_the_rejected_value(self) -> None:
        """graph_entity_extractor logs the exception and continues, so the log
        line is the only trace a caller leaves — it must say what was refused."""
        graph, _ = _graph()

        with pytest.raises(ValueError) as exc_info:
            await graph.create_entity(entity_type="ARTIFACT", name="X", observations=["o"])

        assert "ARTIFACT" in str(exc_info.value)

    async def test_an_empty_name_is_still_rejected_for_an_artifact(self) -> None:
        """The other half of _validate_entity_inputs, on the new types."""
        graph, json_ops = _graph()

        with pytest.raises(ValueError):
            await graph.create_entity(entity_type="DOCUMENT", name="   ", observations=["o"])

        json_ops.set.assert_not_awaited()


class TestApiSchemaFollowsTheVocabulary:
    """POST /api/memory/entities derives its vocabulary, so it cannot lag."""

    @pytest.mark.parametrize("entity_type", ARTIFACT_TYPES)
    def test_the_schema_admits_the_new_types(self, entity_type: str) -> None:
        assert entity_type in _VALID_ENTITY_TYPES

    @pytest.mark.parametrize("entity_type", ARTIFACT_TYPES)
    def test_a_request_carrying_the_type_validates(self, entity_type: str) -> None:
        request = EntityCreateRequest(entity_type=entity_type, name="X", observations=["o"])
        assert request.entity_type == entity_type

    @pytest.mark.parametrize("entity_type", ARTIFACT_TYPES)
    def test_lowercase_is_normalised_at_the_boundary_not_in_the_graph(self, entity_type: str) -> None:
        """The schema upper-cases (#13795); create_entity does not.

        Both halves are asserted so the asymmetry is deliberate rather than
        discovered by a caller whose lower-case write vanished.
        """
        assert EntityCreateRequest(entity_type=entity_type.lower(), name="X", observations=["o"]).entity_type == (
            entity_type
        )
        assert entity_type.lower() not in ENTITY_TYPES


class TestIntentPatternsNameDeclaredTypes:
    """The natural-language mapping is a consumer of the vocabulary."""

    def setup_method(self) -> None:
        self.proc = MemoryGraphQueryProcessor(redis_client=MagicMock())

    def test_every_pattern_target_is_a_declared_type(self) -> None:
        """Nothing validated this before: a pattern could name a type
        create_entity rejects, and the tag filter would simply match nothing."""
        for pattern, types in _ENTITY_TYPE_PATTERNS.items():
            assert set(types) <= ENTITY_TYPES, f"{pattern} names undeclared {set(types) - ENTITY_TYPES}"

    def test_a_document_query_reaches_the_document_type(self) -> None:
        """The word was already matched — it pointed at the activity type."""
        intent = self.proc._extract_intent("which documents did we ingest last week?")
        assert "DOCUMENT" in intent.entity_types

    def test_a_document_query_still_reaches_the_upload_activity(self) -> None:
        """Widened, not redirected: @type:{DOCUMENT|FILE_ACTIVITY} is an OR."""
        intent = self.proc._extract_intent("which documents did we ingest last week?")
        assert "FILE_ACTIVITY" in intent.entity_types

    def test_the_document_type_survives_into_the_redis_filter(self) -> None:
        intent = self.proc._extract_intent("show me the uploaded documents")
        assert "DOCUMENT" in self.proc._build_redis_query(intent)

    def test_code_has_no_intent_pattern_yet(self) -> None:
        """A stated gap, kept executable — #17540.

        `CODE` is declarable and writable but unreachable by natural-language
        search: no pattern names it, and semantic_search.py sits exactly on its
        ratchet ceiling (717/717), so the dict cannot grow until the module is
        split. Closing #17540 must invert this assertion, not delete it
        silently — an absence nothing asserts is how the last vocabulary gap
        stayed invisible.
        """
        reachable = {t for types in _ENTITY_TYPE_PATTERNS.values() for t in types}
        assert "CODE" not in reachable
