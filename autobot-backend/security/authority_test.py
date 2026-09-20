# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The meet of a chain of authorities only ever narrows, and an unused surface narrows nothing (#16950)."""

import pytest

from security.authority import TOP, Authority, meet_all

RICH = Authority(
    approval_gates=frozenset({"writing files"}),
    forbidden_tools=frozenset({"run_command"}),
    permissions=frozenset({"files:write", "files:read"}),
    capabilities=frozenset({"submit_tasks", "query_memory"}),
)


class TestTopIsTheIdentity:
    """A surface a hop does not use is top for it, never bottom -- in both directions."""

    def test_meeting_top_on_the_right_changes_nothing(self):
        assert RICH.meet(TOP) == RICH

    def test_meeting_top_on_the_left_changes_nothing(self):
        assert TOP.meet(RICH) == RICH

    def test_a_hop_without_capabilities_does_not_zero_a_chain_that_has_them(self):
        internal_hop = Authority(forbidden_tools=frozenset({"deploy"}))

        assert internal_hop.meet(RICH).capabilities == RICH.capabilities
        assert RICH.meet(internal_hop).capabilities == RICH.capabilities


class TestMeetNarrows:
    def test_restrictions_accumulate(self):
        other = Authority(approval_gates=frozenset({"publishing"}), forbidden_tools=frozenset({"deploy"}))

        met = RICH.meet(other)

        assert met.approval_gates == {"writing files", "publishing"}
        assert met.forbidden_tools == {"run_command", "deploy"}

    def test_grants_intersect(self):
        other = Authority(permissions=frozenset({"files:read"}), capabilities=frozenset({"submit_tasks"}))

        met = RICH.meet(other)

        assert met.permissions == {"files:read"}
        assert met.capabilities == {"submit_tasks"}

    def test_an_empty_grant_is_bottom_not_top(self):
        """The contrast to top: a hop that grants nothing zeroes the grant for the whole chain."""
        met = RICH.meet(Authority(capabilities=frozenset()))

        assert met.capabilities == frozenset()
        assert not met.has_capability("submit_tasks")

    def test_the_meet_is_commutative_and_idempotent(self):
        other = Authority(permissions=frozenset({"files:read"}), approval_gates=frozenset({"publishing"}))

        assert RICH.meet(other) == other.meet(RICH)
        assert RICH.meet(RICH) == RICH


class TestQueries:
    @pytest.mark.parametrize("permission", ["files:write", "anything:at_all"])
    def test_top_permits_every_permission(self, permission):
        assert TOP.permits(permission)

    def test_a_grant_permits_only_what_it_holds(self):
        assert RICH.permits("files:read")
        assert not RICH.permits("admin:users")

    def test_top_holds_every_capability(self):
        assert TOP.has_capability("any_capability_at_all")


def test_meet_all_of_nothing_is_top():
    assert meet_all() == TOP


def test_meet_all_is_the_chain_meet():
    hops = [RICH, Authority(permissions=frozenset({"files:read"})), Authority(approval_gates=frozenset({"publishing"}))]

    assert meet_all(*hops) == RICH.meet(hops[1]).meet(hops[2])
