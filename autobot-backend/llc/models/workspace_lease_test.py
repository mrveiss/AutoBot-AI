# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A lease must expire, and a released one must never look live (#16818).

The defect this closes is not a wrong answer but an absent one: a workspace had no owner
and no deadline, so "can this be reclaimed" could only be answered by a human reading a
coordination ledger outside the domain. These tests pin the two distinctions that make
the answer mechanical -- held versus expired, and reclaimed versus handed back.
"""

from datetime import datetime, timedelta, timezone

from llc.models.workspace_lease import LLCWorkspaceLease


def _lease(**kw) -> LLCWorkspaceLease:
    now = datetime.now(timezone.utc)
    base = dict(
        path="/w/issue-1",
        owner="autobot-ai-01",
        purpose="issue-1",
        expires_at=now + timedelta(hours=4),
        released_at=None,
    )
    base.update(kw)
    return LLCWorkspaceLease(**base)


def test_a_held_lease_inside_its_window_is_live():
    assert _lease().is_live() is True


def test_a_lease_past_its_deadline_is_not_live():
    """The case that deadlocked the fleet: the holder is gone and nobody can say so."""
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert _lease(expires_at=past).is_live() is False


def test_a_released_lease_is_never_live_even_inside_its_window():
    """A handback must not depend on the clock.

    Releasing early is the normal path; if liveness were decided by expiry alone, a
    workspace returned after ten minutes of a four-hour lease would stay unusable for
    the rest of it -- the ceiling problem this issue exists to end, reintroduced.
    """
    lease = _lease(released_at=datetime.now(timezone.utc))
    assert lease.is_live() is False


def test_release_reason_is_carried_not_inferred():
    """Reclaimed and handed back must be tellable apart.

    Both set released_at. Only the reason says whether the system recovered from an
    abandoned lease or a run returned one cleanly, and an operator asks that first.
    """
    reclaimed = _lease(released_at=datetime.now(timezone.utc), release_reason="run stalled (#16817)")
    returned = _lease(released_at=datetime.now(timezone.utc), release_reason="handed back")
    assert reclaimed.release_reason != returned.release_reason
    assert reclaimed.is_live() is False and returned.is_live() is False


def test_the_table_name_matches_the_migration():
    """A model whose table the migration did not create is a model nothing persists."""
    assert LLCWorkspaceLease.__tablename__ == "llc_workspace_leases"
