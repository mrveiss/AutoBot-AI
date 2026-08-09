# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Drift guard for the canonical relation vocabulary (Issue #13452).

Two independent relation vocabularies used to exist: autobot_memory_graph
spelled the general relation ``related_to`` while knowledge/relations.py
spelled it ``relates_to``, and neither accepted the other's spelling.
``create_relation`` raises ValueError for unknown types and several call sites
swallow it, so every edge written with the wrong spelling was silently dropped
(#13367 fixed one call site; the divergence itself is fixed here).

These tests fail the moment any vocabulary restates names instead of deriving
them from ``autobot_memory_graph.core.CORE_RELATION_TYPES``.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from api.schemas_knowledge import _VALID_RELATION_TYPES, RelationCreateRequest
from autobot_memory_graph import AutoBotMemoryGraph
from autobot_memory_graph.core import (
    CORE_RELATION_TYPES,
    IDENTITY_RELATION_TYPES,
    RELATION_TYPE_ALIASES,
    RELATION_TYPES,
    canonical_relation_filter,
    canonical_relation_type,
    relation_type_matches,
)
from knowledge.relations import KB_RELATION_TYPES, RelationsMixin
from services.security_memory_integration import (
    SECURITY_TO_BASE_RELATION,
    verify_security_relation_vocabulary,
)


class TestCanonicalVocabulary:
    """The canonical set is the only place relation names are declared."""

    def test_kb_vocabulary_derives_from_the_canonical_set(self):
        """knowledge/relations.py must not restate its own list."""
        assert KB_RELATION_TYPES == CORE_RELATION_TYPES

    def test_memory_graph_is_core_plus_identity_relations(self):
        assert RELATION_TYPES == CORE_RELATION_TYPES | IDENTITY_RELATION_TYPES

    def test_identity_relations_are_memory_graph_only(self):
        """owns/has_secret/... are entity relations, meaningless between facts."""
        assert not (IDENTITY_RELATION_TYPES & KB_RELATION_TYPES)

    def test_only_one_spelling_of_the_general_relation_is_live(self):
        """ "relates_to" is an alias, never a member of any live vocabulary."""
        assert "related_to" in CORE_RELATION_TYPES
        for vocabulary in (CORE_RELATION_TYPES, RELATION_TYPES, KB_RELATION_TYPES):
            assert "relates_to" not in vocabulary

    def test_shared_names_have_a_single_spelling(self):
        """Every name the two vocabularies share is character-identical."""
        assert KB_RELATION_TYPES <= RELATION_TYPES


class TestAliases:
    """Aliases map legacy spellings onto canonical names."""

    def test_relates_to_maps_to_related_to(self):
        assert canonical_relation_type("relates_to") == "related_to"

    def test_every_alias_target_is_canonical(self):
        assert set(RELATION_TYPE_ALIASES.values()) <= RELATION_TYPES

    def test_no_alias_shadows_a_live_name(self):
        """An alias key must not also be a valid vocabulary member."""
        assert not (set(RELATION_TYPE_ALIASES) & RELATION_TYPES)

    def test_canonical_names_are_idempotent(self):
        for name in RELATION_TYPES:
            assert canonical_relation_type(name) == name

    def test_unknown_names_pass_through_untouched(self):
        """The helper must not mask a genuine typo."""
        assert canonical_relation_type("nonsense_relation") == "nonsense_relation"


class TestApiSchemaVocabulary:
    """POST /api/memory/relations validates against the memory graph."""

    def test_schema_accepts_every_memory_graph_relation(self):
        """The old literal list rejected related_to, caused_by, owns, ..."""
        assert RELATION_TYPES <= _VALID_RELATION_TYPES

    def test_schema_never_admits_a_type_create_relation_would_reject(self):
        """Anything the validator accepts must survive canonicalisation."""
        for name in _VALID_RELATION_TYPES:
            assert canonical_relation_type(name) in RELATION_TYPES

    @pytest.mark.parametrize("relation_type", ["related_to", "caused_by", "leads_to", "owns"])
    def test_canonical_types_are_accepted(self, relation_type):
        request = RelationCreateRequest(from_entity="a", to_entity="b", relation_type=relation_type)
        assert request.relation_type == relation_type

    def test_legacy_spelling_is_normalised_not_stored(self):
        """A client sending relates_to must persist related_to."""
        request = RelationCreateRequest(from_entity="a", to_entity="b", relation_type="relates_to")
        assert request.relation_type == "related_to"

    def test_unknown_type_is_still_rejected(self):
        with pytest.raises(ValueError):
            RelationCreateRequest(from_entity="a", to_entity="b", relation_type="not_a_relation")


class TestSecurityVocabulary:
    """The security domain's third partial vocabulary maps onto the canonical one."""

    def test_vocabulary_has_not_drifted(self):
        """Runs the module's own guard here rather than at import (#13452).

        Calling it at import would turn a static, source-level mistake into a
        backend startup failure.
        """
        verify_security_relation_vocabulary()

    def test_affects_is_mapped(self):
        """ "affects" is in no canonical set, so it is unusable without a mapping."""
        assert SECURITY_TO_BASE_RELATION["affects"] in RELATION_TYPES


class TestMatcherSymmetry:
    """Reads and deletes must resolve a legacy spelling exactly as writes do."""

    @pytest.mark.parametrize(
        "stored, wanted",
        [
            ("related_to", "relates_to"),  # canonical stored, legacy queried
            ("relates_to", "related_to"),  # legacy stored (pre-#13452), canonical queried
            ("relates_to", "relates_to"),
            ("related_to", "related_to"),
        ],
    )
    def test_alias_and_canonical_are_interchangeable(self, stored, wanted):
        assert relation_type_matches(stored, wanted)

    def test_distinct_types_still_do_not_match(self):
        assert not relation_type_matches("related_to", "depends_on")

    @pytest.mark.parametrize("empty", [None, ""])
    def test_absent_filter_matches_everything(self, empty):
        """An empty filter must mean "all", not "none" — reachable via
        GET /api/knowledge/relations/fact/{id}?relation_type= ."""
        assert relation_type_matches("related_to", empty)

    def test_list_filter_is_canonicalised(self):
        assert canonical_relation_filter(["relates_to", "blocks"]) == {"related_to", "blocks"}

    @pytest.mark.parametrize("empty", [None, []])
    def test_absent_list_filter_is_none(self, empty):
        assert canonical_relation_filter(empty) is None

    def test_kb_reuses_the_shared_matcher(self):
        """One matcher, so the two stores cannot drift in how they resolve aliases."""
        assert RelationsMixin._relation_type_matches is relation_type_matches


class TestMemoryGraphRoundTrip:
    """Write with the alias, then read and delete by it (#13452 blocker).

    Writes canonicalise, so without the same normalisation on the read and
    delete paths a relation created as "relates_to" is stored as "related_to"
    and then unreachable: GET returns 0 rows, DELETE 404s, invalidate no-ops.
    """

    @staticmethod
    def _graph(stored_relations=None):
        """Build a graph whose redis_client.json() is sync but its ops async."""
        graph = AutoBotMemoryGraph()
        graph._initialized = True
        json_ops = Mock()
        json_ops.get = AsyncMock(return_value={"relations": list(stored_relations or [])})
        json_ops.set = AsyncMock()
        graph.redis_client = Mock()
        graph.redis_client.json = Mock(return_value=json_ops)
        return graph, json_ops

    async def test_write_stores_the_canonical_spelling(self):
        graph, _ = self._graph()
        graph._resolve_entity_ids = AsyncMock(return_value=("id-a", "id-b"))
        graph._store_outgoing_relation = AsyncMock()
        graph._store_incoming_relation = AsyncMock()

        relation = await graph.create_relation("A", "B", relation_type="relates_to")

        assert relation["type"] == "related_to"

    async def test_get_relations_finds_it_by_the_alias(self):
        graph, _ = self._graph()
        graph._get_outgoing_relations = AsyncMock(return_value=[{"to": "id-b", "type": "related_to"}])
        graph._get_incoming_relations = AsyncMock(return_value=[])

        result = await graph.get_relations("id-a", relation_types=["relates_to"])

        assert len(result["relations"]) == 1

    async def test_get_relations_finds_legacy_rows_by_the_canonical_name(self):
        """Rows persisted before #13452 still carry the alias in Redis."""
        graph, _ = self._graph()
        graph._get_outgoing_relations = AsyncMock(return_value=[{"to": "id-b", "type": "relates_to"}])
        graph._get_incoming_relations = AsyncMock(return_value=[])

        result = await graph.get_relations("id-a", relation_types=["related_to"])

        assert len(result["relations"]) == 1

    async def test_get_related_entities_traverses_through_the_alias(self):
        graph, _ = self._graph()
        graph.get_entity = AsyncMock(return_value={"id": "id-a", "name": "A"})
        # Only id-a has an outgoing edge, so the BFS terminates at id-b.
        graph._get_outgoing_relations = AsyncMock(
            side_effect=lambda eid: [{"to": "id-b", "type": "related_to"}] if eid == "id-a" else []
        )
        graph._get_incoming_relations = AsyncMock(return_value=[])

        related = await graph.get_related_entities("A", relation_type="relates_to", direction="outgoing")

        assert len(related) == 1
        assert related[0]["relation"]["type"] == "related_to"

    async def test_delete_relation_removes_it_when_asked_by_the_alias(self):
        graph, json_ops = self._graph([{"to": "id-b", "from": "id-a", "type": "related_to"}])
        graph.get_entity = AsyncMock(side_effect=[{"id": "id-a"}, {"id": "id-b"}])

        assert await graph.delete_relation("A", "B", relation_type="relates_to") is True

        # Both directions rewritten with the matching relation removed.
        assert json_ops.set.call_count == 2
        for call in json_ops.set.call_args_list:
            assert call.args[2] == []

    async def test_delete_relation_leaves_other_types_alone(self):
        graph, json_ops = self._graph([{"to": "id-b", "from": "id-a", "type": "depends_on"}])
        graph.get_entity = AsyncMock(side_effect=[{"id": "id-a"}, {"id": "id-b"}])

        await graph.delete_relation("A", "B", relation_type="relates_to")

        for call in json_ops.set.call_args_list:
            assert len(call.args[2]) == 1

    async def test_invalidate_relation_matches_through_the_alias(self):
        graph, _ = self._graph([{"to": "id-b", "from": "id-a", "type": "related_to"}])

        assert await graph.invalidate_relation("id-a", "relates_to", "id-b") is True


class TestPropertyGraphMirrorLabel:
    """The property-graph mirror must carry the same label the JSON store did.

    PropertyGraphMixin.create_relation is the live override (first in
    AutoBotMemoryGraph's MRO), so every write goes through it. It calls
    super().create_relation, which canonicalises, then mirrors the edge into the
    property graph. Labelling that edge from the caller's raw spelling persisted
    "related_to" in Redis JSON but RELATES_TO in the pg:adj:* index — a
    divergence nothing canonicalises later (#13452).
    """

    @staticmethod
    def _graph():
        graph = AutoBotMemoryGraph()
        graph._initialized = True
        graph.redis_client = Mock()
        graph._resolve_entity_ids = AsyncMock(return_value=("id-a", "id-b"))
        graph._store_outgoing_relation = AsyncMock()
        graph._store_incoming_relation = AsyncMock()
        graph.get_entity = AsyncMock(
            side_effect=lambda **kw: {"id": "id-a" if kw.get("entity_name") == "A" else "id-b"}
        )
        property_graph = Mock()
        property_graph.add_edge = AsyncMock(return_value="edge-1")
        graph._property_graph = property_graph
        return graph, property_graph

    async def test_alias_write_mirrors_the_canonical_label(self):
        graph, property_graph = self._graph()

        await graph.create_relation("A", "B", relation_type="relates_to")

        property_graph.add_edge.assert_awaited_once()
        assert property_graph.add_edge.await_args.args[2] == "RELATED_TO"

    async def test_bidirectional_reverse_edge_uses_the_canonical_label_too(self):
        graph, property_graph = self._graph()

        await graph.create_relation("A", "B", relation_type="relates_to", bidirectional=True)

        assert property_graph.add_edge.await_count == 2
        for call in property_graph.add_edge.await_args_list:
            assert call.args[2] == "RELATED_TO"

    async def test_canonical_write_is_unchanged(self):
        graph, property_graph = self._graph()

        await graph.create_relation("A", "B", relation_type="depends_on")

        assert property_graph.add_edge.await_args.args[2] == "DEPENDS_ON"

    async def test_mirror_label_matches_what_the_json_store_recorded(self):
        """The two stores must agree by construction, not by coincidence."""
        graph, property_graph = self._graph()

        relation = await graph.create_relation("A", "B", relation_type="relates_to")

        assert property_graph.add_edge.await_args.args[2] == relation["type"].upper()


class TestUserSessionVocabulary:
    """has_session / has_activity / uses_secret must be writable (#13452).

    None of the three was declared, so create_relation_by_id raised ValueError
    on every one. create_chat_session_entity re-raises, so chat-session creation
    failed outright after "owns" had already been written — a half-built graph —
    and get_user_sessions then filtered on names that could never match.
    """

    @pytest.mark.parametrize("relation_type", ["owns", "has_session", "has_participant"])
    def test_session_relations_are_declared(self, relation_type):
        assert relation_type in RELATION_TYPES

    @pytest.mark.parametrize("relation_type", ["has_activity", "performed_by"])
    def test_activity_relations_are_declared(self, relation_type):
        assert relation_type in RELATION_TYPES

    def test_uses_secret_maps_onto_the_declared_tense(self):
        """ "used_secret" is the declared #608 name but had no writer;
        "uses_secret" is what user_session.py emits. One relation, one spelling."""
        assert canonical_relation_type("uses_secret") == "used_secret"
        assert "uses_secret" not in RELATION_TYPES

    def test_session_relations_are_identity_tier_not_knowledge_base(self):
        for relation_type in ("has_session", "has_activity"):
            assert relation_type in IDENTITY_RELATION_TYPES
            assert relation_type not in KB_RELATION_TYPES

    async def test_create_relation_by_id_accepts_every_user_session_type(self):
        """The three writers in user_session.py must all reach storage."""
        graph = AutoBotMemoryGraph()
        graph._initialized = True
        graph.redis_client = Mock()
        graph._store_outgoing_relation = AsyncMock()
        graph._store_incoming_relation = AsyncMock()

        for relation_type in ("has_session", "has_activity", "uses_secret"):
            assert await graph.create_relation_by_id("id-a", "id-b", relation_type) is True

    async def test_get_relations_filter_matches_what_user_session_writes(self):
        """get_user_sessions filters on ["owns", "has_session"] (#13452)."""
        graph = AutoBotMemoryGraph()
        graph._initialized = True
        graph.redis_client = Mock()
        graph._get_outgoing_relations = AsyncMock(
            return_value=[{"to": "sess-1", "type": "has_session"}, {"to": "sec-1", "type": "used_secret"}]
        )
        graph._get_incoming_relations = AsyncMock(return_value=[])

        result = await graph.get_relations("user-1", relation_types=["owns", "has_session"], direction="outgoing")

        assert len(result["relations"]) == 1
