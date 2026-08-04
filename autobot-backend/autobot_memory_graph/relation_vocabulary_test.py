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

import pytest

from api.schemas_knowledge import _VALID_RELATION_TYPES, RelationCreateRequest
from autobot_memory_graph.core import (
    CORE_RELATION_TYPES,
    IDENTITY_RELATION_TYPES,
    RELATION_TYPE_ALIASES,
    RELATION_TYPES,
    canonical_relation_type,
)
from knowledge.relations import KB_RELATION_TYPES
from services.security_memory_integration import (
    SECURITY_RELATION_TYPES,
    SECURITY_TO_BASE_RELATION,
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

    def test_every_security_relation_maps_to_a_canonical_type(self):
        assert set(SECURITY_TO_BASE_RELATION.values()) <= RELATION_TYPES

    def test_documented_and_mapped_tables_agree(self):
        assert set(SECURITY_RELATION_TYPES) == set(SECURITY_TO_BASE_RELATION)

    def test_affects_is_mapped(self):
        """ "affects" is in no canonical set, so it is unusable without a mapping."""
        assert SECURITY_TO_BASE_RELATION["affects"] in RELATION_TYPES
