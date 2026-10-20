# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""End-to-end proof of the shared research-quarantine filter (#13009).

#12622 introduced the quarantine ``{"collection": {"$ne": ...}}`` filter at a
single call site (``async_chat_workflow.py::_execute_kb_search``). #13009
audited every other reachable, general-purpose ``kb.search()`` call site,
found several more with the same gap, and extracted the filter into this
module so it is defined exactly once.

This test proves the filter mechanism itself, the same way #13011's
``services/research/quarantine_boundary_test.py`` proved it for the
promotion gate: driving a real (non-mocked) ``InMemoryClient`` where-filter,
not a mock. Per-call-site tests (in each touched module's test file) prove
the filter is actually *passed* at each of the #13009 call sites; this test
proves that, once passed, it actually excludes/includes the right facts.
"""

from __future__ import annotations

from autobot_shared.ssot_config import config
from knowledge.backends import InMemoryClient
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER


def _collection():
    """A real (non-mocked) in-memory vector-store collection."""
    return InMemoryClient().get_or_create_collection("quarantine_filter_test")


class TestResearchQuarantineFilter:
    """Real where-filter proof for the shared #13009 filter constant."""

    def test_filter_derives_from_config_not_hardcoded(self):
        """The filter must track the SSOT config constant (#12623), never a literal.

        #18820: it also carries the serving predicate's store-side trust clause.
        """
        assert RESEARCH_QUARANTINE_FILTER == {
            "$and": [
                {"collection": {"$ne": config.research_quarantine_collection}},
                {"verification_status": {"$ne": "rejected"}},
            ]
        }

    def test_quarantined_fact_is_excluded(self):
        collection = _collection()
        collection.add(
            ids=["quarantined-fact"],
            metadatas=[{"collection": config.research_quarantine_collection, "fact_id": "quarantined-fact"}],
        )

        visible = collection.get(where=RESEARCH_QUARANTINE_FILTER)

        assert "quarantined-fact" not in visible["ids"]

    def test_promoted_fact_is_included(self):
        collection = _collection()
        collection.add(
            ids=["promoted-fact"],
            metadatas=[{"collection": config.research_quarantine_collection, "fact_id": "promoted-fact"}],
        )
        before = collection.get(where=RESEARCH_QUARANTINE_FILTER)
        assert "promoted-fact" not in before["ids"]

        collection.update(ids=["promoted-fact"], metadatas=[{"collection": "general", "fact_id": "promoted-fact"}])

        after = collection.get(where=RESEARCH_QUARANTINE_FILTER)
        assert "promoted-fact" in after["ids"]

    def test_legacy_fact_without_collection_field_stays_included(self):
        """Facts predating #12622 (no 'collection' key at all) must not be hidden."""
        collection = _collection()
        collection.add(ids=["legacy-fact"], metadatas=[{"fact_id": "legacy-fact"}])

        visible = collection.get(where=RESEARCH_QUARANTINE_FILTER)

        assert "legacy-fact" in visible["ids"]


class TestGroundingFilterTrustClause:
    """#18820: the shared grounding filter never lets a rejected fact through the store.

    Unverified and pending_review facts keep today's behaviour -- served -- until the
    open #18077 decision is made; these tests pin that, so flipping it is a visible change.
    """

    @staticmethod
    def _visible(status):
        collection = _collection()
        metadata = {"fact_id": "f"} if status is None else {"fact_id": "f", "verification_status": status}
        collection.add(ids=["f"], metadatas=[metadata])
        return "f" in collection.get(where=RESEARCH_QUARANTINE_FILTER)["ids"]

    def test_a_rejected_fact_is_excluded(self):
        assert self._visible("rejected") is False

    def test_a_verified_fact_is_included(self):
        """Positive control for the rejected case."""
        assert self._visible("verified") is True

    def test_unverified_and_pending_review_are_unchanged_until_18077(self):
        assert self._visible("unverified") is True
        assert self._visible("pending_review") is True

    def test_a_fact_with_no_verification_status_stays_included(self):
        """Legacy facts predate the field; the clause must not hide them."""
        assert self._visible(None) is True

    def test_a_rejected_fact_outside_quarantine_is_still_excluded(self):
        collection = _collection()
        collection.add(ids=["f"], metadatas=[{"collection": "general", "verification_status": "rejected"}])
        assert "f" not in collection.get(where=RESEARCH_QUARANTINE_FILTER)["ids"]
