# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`ReviewTicketPriority` is the canonical `Priority` (#18098, #18086).

Expected wire values are LITERALS captured from the old three-member enum, never derived from
the code under test: the ticket JSON carries `priority.value` and the review queue key is
`review_queue:<value>`.
"""

from __future__ import annotations

import json

from autobot_shared.status_enums import Priority

OLD_WIRE = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def test_review_ticket_priority_is_the_canonical_priority():
    from api.knowledge_grounding_models import ReviewTicketPriority

    assert ReviewTicketPriority is Priority


def test_the_three_members_the_resolver_assigns_keep_their_wire_values():
    from api.knowledge_grounding_models import ReviewTicketPriority

    assert {name: ReviewTicketPriority[name].value for name in OLD_WIRE} == OLD_WIRE
    assert [ReviewTicketPriority(v) for v in OLD_WIRE.values()] == [ReviewTicketPriority[n] for n in OLD_WIRE]


def test_the_persisted_ticket_and_queue_key_are_byte_identical():
    from api.knowledge_grounding_models import ReviewTicketPriority

    for name, wire in OLD_WIRE.items():
        priority = ReviewTicketPriority[name]
        assert json.dumps({"priority": priority.value}) == '{"priority": "%s"}' % wire
        assert f"review_queue:{priority.value}" == f"review_queue:{wire}"


def test_members_still_equal_their_wire_strings():
    from api.knowledge_grounding_models import ReviewTicketPriority

    for name, wire in OLD_WIRE.items():
        assert ReviewTicketPriority[name] == wire
