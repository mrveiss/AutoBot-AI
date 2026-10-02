# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A workspace is leased, reclaimed on expiry, and disposed of only on evidence (#16818).

AC6 names two of these: an expired lease is reclaimed and its directory disposed, and a
live lease is never reclaimed. The rest exist because the interesting failures here are
all silent -- a lease that frees no capacity, a reclaim that runs twice, a disposal that
removes work nobody pushed. None of those raise; they just lose something.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from llc.models.workspace_lease import LLCWorkspaceLease
from llc.services import workspace_disposal as disposal
from llc.services import workspace_lease as svc

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
COMPANY = uuid.uuid4()


def _lease(**kw) -> LLCWorkspaceLease:
    base = {
        "id": uuid.uuid4(),
        "company_id": COMPANY,
        "path": "/w/issue-1",
        "owner": "session-a",
        "purpose": "issue #1",
        "acquired_at": NOW - timedelta(hours=5),
        "expires_at": NOW + timedelta(hours=1),
        "released_at": None,
        "release_reason": None,
        "heartbeat_run_id": None,
        "branch": None,
    }
    base.update(kw)
    return LLCWorkspaceLease(**base)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._rows[0] if self._rows else 0


class _Session:
    """Returns queued results in call order, and records what it was asked."""

    def __init__(self, *results):
        self._queue = list(results)
        self.added = []
        self.flushed = False
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._queue.pop(0) if self._queue else [])

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def commit(self):
        pass


# ---------------------------------------------------------------------------
# is_live -- the predicate everything else is built on
# ---------------------------------------------------------------------------


def test_a_released_lease_is_never_live_however_far_off_its_expiry():
    """Otherwise a handed-back workspace keeps occupying a slot until its deadline,
    which is the ceiling behaving exactly as it did before leases existed."""
    lease = _lease(released_at=NOW, expires_at=NOW + timedelta(days=30))
    assert lease.is_live(NOW) is False


def test_a_held_lease_past_its_deadline_is_not_live():
    assert _lease(expires_at=NOW - timedelta(seconds=1)).is_live(NOW) is False


# ---------------------------------------------------------------------------
# AC6, second half: a live lease is never reclaimed
# ---------------------------------------------------------------------------


def test_the_expired_selection_asks_for_held_and_past_deadline_only():
    """The reclaim's whole safety property is in this WHERE clause. Compiled against
    the postgres dialect because the default one silently drops SKIP LOCKED."""
    sql = str(svc.expired_lease_select(NOW).compile(dialect=postgresql.dialect()))
    assert "released_at IS NULL" in sql, "a released lease must not be reclaimed again"
    assert "expires_at <=" in sql, "a live lease must not be reclaimed"
    assert "SKIP LOCKED" in sql, "two sweeps must partition, not collide"


@pytest.mark.asyncio
async def test_a_live_lease_is_not_reclaimed_even_if_the_query_hands_one_over():
    """AC6 as stated, and deliberately harsher than the AC.

    The SQL already excludes live leases, so a test feeding the real query proves
    nothing about the code -- it proves the database filtered. This hands `reclaim_expired`
    a live lease directly, which is what a mistyped WHERE clause would do, and requires
    the reclaim to refuse it anyway. Remove the Python guard and only this test fails.
    """
    live = _lease(expires_at=NOW + timedelta(hours=3))
    expired = _lease(path="/w/old", expires_at=NOW - timedelta(minutes=1))
    session = _Session([live, expired])

    reclaimed = await svc.reclaim_expired(session, now=NOW)

    assert reclaimed == [expired], "only the expired lease may be taken back"
    assert live.released_at is None and live.release_reason is None


@pytest.mark.asyncio
async def test_an_expired_lease_is_reclaimed_with_a_reason_not_just_a_timestamp():
    expired = _lease(expires_at=NOW - timedelta(hours=2))
    session = _Session([expired])

    reclaimed = await svc.reclaim_expired(session, now=NOW)

    assert reclaimed == [expired]
    assert expired.released_at == NOW
    assert expired.release_reason == svc.RECLAIM_REASON
    assert "expired" in expired.release_reason


def test_release_is_idempotent_and_keeps_the_first_reason():
    """A clean handback must not be rewritten as a reclaim by a sweep that runs after.

    Without this the audit trail describes a recovery that never happened, and
    'the system worked' and 'the system recovered' become indistinguishable --
    which is the distinction the two reasons exist to draw.
    """
    lease = _lease()
    svc.release(lease, "handed back", now=NOW)
    svc.release(lease, svc.RECLAIM_REASON, now=NOW + timedelta(hours=1))

    assert lease.release_reason == "handed back"
    assert lease.released_at == NOW


@pytest.mark.asyncio
async def test_release_for_run_releases_every_lease_that_run_held():
    """#16817's sweep calls this. A run holding two workspaces must hand back both."""
    one, two = _lease(path="/w/a"), _lease(path="/w/b")
    session = _Session([one, two])

    released = await svc.release_for_run(session, uuid.uuid4(), "run stalled", now=NOW)

    assert len(released) == 2
    assert all(le.released_at == NOW and le.release_reason == "run stalled" for le in (one, two))


# ---------------------------------------------------------------------------
# AC5: the ceiling is a consequence of leases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_reclaims_expired_leases_before_counting_capacity(monkeypatch):
    """The deadlock of 2026-09-16, as a test.

    Every slot held, every holder gone. If capacity were counted before the reclaim,
    acquire would refuse and the fleet would stay blocked exactly as it did -- so the
    ordering, not merely the reclaim's existence, is the fix.
    """
    monkeypatch.setattr(svc, "WORKSPACE_CAP", 1)
    expired = _lease(path="/w/old", expires_at=NOW - timedelta(hours=2))
    # reclaim -> the expired lease; lease_for_path -> none; live count -> 0 after reclaim
    session = _Session([expired], [], [0])

    lease = await svc.acquire_lease(
        session, company_id=COMPANY, path="/w/new", owner="session-b", purpose="issue #2", now=NOW
    )

    assert expired.released_at == NOW, "the blocking lease must have been reclaimed"
    assert lease in session.added
    assert lease.expires_at == NOW + timedelta(seconds=svc.LEASE_TTL_SECONDS)


@pytest.mark.asyncio
async def test_acquire_refuses_a_path_that_carries_a_live_lease():
    held = _lease(path="/w/busy", owner="session-a")
    session = _Session([], [held])

    with pytest.raises(svc.WorkspaceLeaseHeld) as exc:
        await svc.acquire_lease(session, company_id=COMPANY, path="/w/busy", owner="session-b", purpose="p", now=NOW)

    assert "session-a" in str(exc.value), "the refusal must name who holds it"
    assert session.added == []


@pytest.mark.asyncio
async def test_a_full_fleet_of_live_leases_is_a_different_error_from_a_busy_path(monkeypatch):
    """Both refuse an acquire; only one is fixable by waiting for a deadline. On
    2026-09-16 they were indistinguishable and the cap's message sent people to the
    wrong remedy."""
    monkeypatch.setattr(svc, "WORKSPACE_CAP", 2)
    session = _Session([], [], [2])

    with pytest.raises(svc.WorkspaceCapacityExhausted):
        await svc.acquire_lease(session, company_id=COMPANY, path="/w/new", owner="session-b", purpose="p", now=NOW)
    assert session.added == []


@pytest.mark.asyncio
async def test_a_released_lease_does_not_block_reacquiring_its_path():
    """Migration 097's reason, asserted at the service. `lease_for_path` must ignore
    released rows, or a directory becomes unusable the moment it is handed back once."""
    session = _Session([], [], [0])

    lease = await svc.acquire_lease(
        session, company_id=COMPANY, path="/w/reused", owner="session-c", purpose="p", now=NOW
    )

    assert lease.path == "/w/reused"


# ---------------------------------------------------------------------------
# AC7: disposal is evidence-based, and "unknown" is not "safe"
# ---------------------------------------------------------------------------


def _git_returning(*pairs):
    """Stub `_git` with a queued (returncode, output) per call."""
    queue = list(pairs)

    async def _fake(*args, cwd=None):
        return queue.pop(0) if queue else (0, "")

    return _fake


@pytest.mark.asyncio
async def test_uncommitted_changes_block_disposal(monkeypatch, tmp_path):
    monkeypatch.setattr(disposal, "_git", _git_returning((0, " M autobot-backend/x.py")))

    check = await disposal.work_landed(str(tmp_path))

    assert check.verdict is disposal.DisposalVerdict.NOT_LANDED
    assert check.may_dispose is False
    assert "uncommitted" in check.detail


@pytest.mark.asyncio
async def test_commits_on_no_remote_block_disposal(monkeypatch, tmp_path):
    monkeypatch.setattr(disposal, "_git", _git_returning((0, ""), (0, "abc1234 feat: unpushed")))

    check = await disposal.work_landed(str(tmp_path), branch="issue-1")

    assert check.verdict is disposal.DisposalVerdict.NOT_LANDED
    assert "no remote" in check.detail


@pytest.mark.asyncio
async def test_a_git_failure_is_unknown_and_still_refuses(monkeypatch, tmp_path):
    """The one that matters most.

    A failed measurement must not read as a clean one. If UNKNOWN were ever treated
    as disposable, every transient git error would delete a workspace -- the failure
    mode is silent, permanent and indistinguishable from correct operation.
    """
    monkeypatch.setattr(disposal, "_git", _git_returning((-1, "OSError: no git")))

    check = await disposal.work_landed(str(tmp_path))

    assert check.verdict is disposal.DisposalVerdict.UNKNOWN
    assert check.may_dispose is False


@pytest.mark.asyncio
async def test_a_missing_directory_is_unknown_not_landed(monkeypatch):
    check = await disposal.work_landed("/does/not/exist/anywhere")
    assert check.verdict is disposal.DisposalVerdict.UNKNOWN


@pytest.mark.asyncio
async def test_a_clean_pushed_worktree_is_landed(monkeypatch, tmp_path):
    monkeypatch.setattr(disposal, "_git", _git_returning((0, ""), (0, "")))

    check = await disposal.work_landed(str(tmp_path), branch="issue-1")

    assert check.verdict is disposal.DisposalVerdict.LANDED
    assert check.may_dispose is True


@pytest.mark.asyncio
async def test_disposal_removes_without_force_and_only_after_the_check(monkeypatch, tmp_path):
    """AC6's first half, and the reason `--force` is absent.

    Git refuses a worktree it considers unsafe, and that refusal is the last guard
    standing between a wrong verdict and lost work. Asserting the flag is absent is
    the only way that stays true -- adding it would break nothing else here.
    """
    calls = []

    async def _fake(*args, cwd=None):
        calls.append(args)
        return (0, "")

    monkeypatch.setattr(disposal, "_git", _fake)

    check = await disposal.dispose_workspace(str(tmp_path), branch="issue-1")

    assert check.verdict is disposal.DisposalVerdict.LANDED
    assert ("worktree", "remove", str(tmp_path)) in calls
    assert not any("--force" in a or "-f" in a for a in calls), "a dirty tree refusing to go is information"


@pytest.mark.asyncio
async def test_nothing_is_removed_when_the_check_refuses(monkeypatch, tmp_path):
    calls = []

    async def _fake(*args, cwd=None):
        calls.append(args)
        return (0, " M x.py") if args[0] == "status" else (0, "")

    monkeypatch.setattr(disposal, "_git", _fake)

    check = await disposal.dispose_workspace(str(tmp_path))

    assert check.may_dispose is False
    assert not any(a[0] == "worktree" for a in calls), "a refused disposal must not touch the directory"


# ---------------------------------------------------------------------------
# The model and the migration must agree (87's finding on #17725)
# ---------------------------------------------------------------------------


def test_the_model_declares_no_table_wide_unique_on_path():
    """The disagreement that survived its own fix.

    097 drops `uq_llc_workspace_leases_path`, but the model kept `unique=True` on the
    column — so a database built from the models (a fixture's create_all, a fresh dev
    box) would carry the constraint the migration removes and reproduce the bug, with
    nothing in the tree comparing the two.
    """
    column = LLCWorkspaceLease.__table__.c.path
    assert column.unique is not True, "a table-wide UNIQUE burns the path on its first release"


def test_the_partial_predicate_is_weaker_than_is_live_and_the_gap_is_the_reclaim():
    """Documents the state the index cannot see. **This does not pin the invariant.**

    Both assertions below are true by construction — there is no index here and no
    database — so this is a worked example, not a guard, and saying otherwise would be
    the more dangerous error: a test that reads as protection and provides none.

    What actually fails if the reclaim is removed is
    `test_acquire_reclaims_expired_leases_before_counting_capacity`. What fails if the
    model and migration drift apart is
    `repo_tests/workspace_lease_index_matches_migration_16818_test.py`. This one exists
    so the next reader can see, concretely, which lease state falls in the gap between
    `is_live()` and a predicate that cannot call `now()`.
    """
    expired_unreleased = _lease(expires_at=NOW - timedelta(hours=1), released_at=None)

    assert expired_unreleased.is_live(NOW) is False, "is_live says not live"
    assert expired_unreleased.released_at is None, "but the index predicate still counts it as present"
