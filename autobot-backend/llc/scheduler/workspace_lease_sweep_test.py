# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The workspace sweep frees slots itself and asks a human before removing anything (#16818, #17038).

Two properties carry the design, and both fail loudly here if merged back together:

* reclaiming is committed before any directory is touched, so a refused disposal never
  costs the capacity that was the point of reclaiming; and
* **no directory is removed without an approved proposal**, and an approved proposal's
  evidence is re-proved at execution rather than trusted.
"""

import importlib
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest

from llc.services.workspace_disposal import DisposalCheck, DisposalVerdict

COMPANY = uuid.uuid4()


@pytest.fixture
def sweep():
    return importlib.reload(importlib.import_module("llc.scheduler.workspace_lease_sweep"))


def _compiled_limit(statement) -> "int | None":
    """The LIMIT in *statement*, read from its compiled SQL, or None if it has none.

    None means "this statement does not limit", which is a legitimate answer --
    most of the sweep's queries do not. What it must never mean is "there is a
    limit and I could not find it", which is what reading two private attributes
    produced when either moved.
    """
    import re

    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    match = re.search(r"\bLIMIT\s+(\d+)", sql, re.IGNORECASE)
    return int(match.group(1)) if match else None


class _Session:
    def __init__(self, approvals=None):
        self.committed = False
        self._approvals = approvals
        self.statements = [] or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def execute(self, statement):
        # The fake HONOURS a SQL LIMIT. Without this it silently ignores one, and a test
        # asserting "the backlog does not hide the unexecuted proposal" passes whether or
        # not the LIMIT is there -- a test that cannot fail, which is the exact defect
        # this suite exists to catch one level up.
        #
        # #17739: read from the COMPILED SQL, not from `statement._limit` /
        # `statement._limit_clause.value`. Those are SQLAlchemy internals, and when
        # they moved the fake would have found neither, left `limit = None`, and
        # silently stopped applying limits -- taking the regression test with it,
        # quietly. `str(statement.compile(...))` is the public surface and says LIMIT
        # in every version that emits one. `test_the_fake_session_honours_a_limit`
        # below fails if this stops working, so the degradation cannot be silent.
        rows = self._approvals
        # Recorded so a test can assert WHICH predicates the query carried.
        # Without this, removing a WHERE clause from the sweep's query left every
        # test green -- the fake does not filter, so a missing predicate is
        # invisible to any assertion about the rows that come back.
        self.statements.append(statement)
        limit = _compiled_limit(statement)
        if limit is not None:
            rows = rows[:limit]

        class _R:
            def scalars(self):
                return self

            def all(self):
                return rows

        return _R()

    async def commit(self):
        self.committed = True


def _lease(path="/w/merged", branch="issue-1"):
    return SimpleNamespace(path=path, branch=branch, company_id=COMPANY)


def _approval(paths, executed=False):
    context = {
        "kind": "workspace_disposal",
        "workspaces": [{"path": p, "branch": "b"} for p in paths],
    }
    if executed:
        context["executed_at"] = "2026-09-28T00:00:00+00:00"
    # `id` because the real model has one (llc/models/approval.py:42) and the
    # aged-out warning names the approvals it skipped. A double missing a column
    # the model declares does not simplify the test, it just moves the failure.
    return SimpleNamespace(context=context, id=uuid.uuid4())


def _install(sweep, monkeypatch, *, reclaimed=(), landed=None, approvals=(), disposals=None, leases=None):
    session = _Session(list(approvals))
    session.published = []
    monkeypatch.setattr(sweep, "get_async_session_factory", lambda: (lambda: session))

    async def _reclaim(_s, now=None):
        return list(reclaimed)

    async def _landed(path, branch=None):
        return (landed or {}).get(path, DisposalCheck(DisposalVerdict.LANDED, "on a remote"))

    async def _dispose(path, branch):
        assert session.committed is False, "disposal runs inside the sweep transaction"
        return (disposals or {}).get(path, DisposalCheck(DisposalVerdict.LANDED, "on a remote"))

    requested = []

    class _Approvals:
        async def request_approval(self, _s, **kwargs):
            requested.append(kwargs)
            return SimpleNamespace(id=uuid.uuid4())

        async def publish_requested(self, approval):
            # Recorded WITH the commit state, because the contract is ordering rather
            # than occurrence: publish_requested's own docstring says to call it AFTER
            # the transaction commits, and a publish inside the transaction announces a
            # proposal a rollback could still erase.
            session.published.append((approval, session.committed))

    async def _lease_for_path(_s, path):
        return (leases or {}).get(path)

    monkeypatch.setattr(sweep, "lease_for_path", _lease_for_path)
    monkeypatch.setattr(sweep, "reclaim_expired", _reclaim)
    monkeypatch.setattr(sweep, "work_landed", _landed)
    monkeypatch.setattr(sweep, "dispose_workspace", _dispose)
    monkeypatch.setattr(sweep, "ApprovalService", _Approvals)
    return session, requested


# ---------------------------------------------------------------------------
# #17038: propose, never remove unattended
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_landed_workspace_is_proposed_for_approval_and_not_removed(sweep, monkeypatch):
    """The owner's ruling, as the sweep's central assertion.

    Mutation-checked: restore the old behaviour -- call `dispose_workspace` on a freshly
    reclaimed lease -- and this fails, because nothing may be disposed without an
    approval that already exists.
    """
    disposed_paths = []

    async def _never(path, branch):
        disposed_paths.append(path)
        return DisposalCheck(DisposalVerdict.LANDED, "on a remote")

    session, requested = _install(sweep, monkeypatch, reclaimed=[_lease()])
    monkeypatch.setattr(sweep, "dispose_workspace", _never)

    result = await sweep._async_sweep()

    assert result == {"reclaimed": 1, "disposed": 0, "refused": 0, "proposed": 1}
    assert disposed_paths == [], "nothing may be removed without an approved proposal"
    assert len(requested) == 1, "a proposal must be raised"


@pytest.mark.asyncio
async def test_the_proposal_carries_the_evidence_not_just_the_path(sweep, monkeypatch):
    """A reviewer approving a deletion needs the reason it is safe on the record they
    approve, not in a worker's log that they cannot see."""
    session, requested = _install(
        sweep,
        monkeypatch,
        reclaimed=[_lease()],
        landed={"/w/merged": DisposalCheck(DisposalVerdict.LANDED, "branch issue-1 is fully present on a remote")},
    )

    await sweep._async_sweep()

    payload = requested[0]["payload"]
    assert payload["kind"] == "workspace_disposal"
    entry = payload["workspaces"][0]
    assert entry["path"] == "/w/merged"
    assert "remote" in entry["evidence"], "the landedness proof must travel with the proposal"
    assert requested[0]["requested_by"] == sweep.SWEEP_REQUESTER


@pytest.mark.asyncio
async def test_a_workspace_that_did_not_land_is_never_proposed(sweep, monkeypatch):
    """The slot still comes back; the directory is not even offered for deletion."""
    session, requested = _install(
        sweep,
        monkeypatch,
        reclaimed=[_lease(path="/w/unpushed")],
        landed={"/w/unpushed": DisposalCheck(DisposalVerdict.NOT_LANDED, "2 commits on no remote")},
    )

    result = await sweep._async_sweep()

    assert result["proposed"] == 0
    assert requested == [], "a workspace with unpushed work must not reach a reviewer as disposable"
    assert result["reclaimed"] == 1 and session.committed, "the slot is freed regardless"


@pytest.mark.asyncio
async def test_an_unknown_verdict_is_not_proposed_either(sweep, monkeypatch):
    _, requested = _install(
        sweep,
        monkeypatch,
        reclaimed=[_lease(path="/w/broken")],
        landed={"/w/broken": DisposalCheck(DisposalVerdict.UNKNOWN, "git failed")},
    )
    assert (await sweep._async_sweep())["proposed"] == 0
    assert requested == []


# ---------------------------------------------------------------------------
# Executing what a human approved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_approved_proposal_is_executed(sweep, monkeypatch):
    _, _ = _install(sweep, monkeypatch, approvals=[_approval(["/w/ok"])])

    result = await sweep._async_sweep()

    assert result["disposed"] == 1 and result["refused"] == 0


@pytest.mark.asyncio
async def test_landedness_is_proved_again_at_execution_not_trusted_from_the_proposal(sweep, monkeypatch):
    """The gap approval opens.

    A proposal approved hours ago describes the directory as it was hours ago. Someone may
    have worked in it since. The approval authorises the removal; it does not vouch for
    the evidence, so the check runs again and can still refuse.
    """
    approval = _approval(["/w/changed"])
    _, _ = _install(
        sweep,
        monkeypatch,
        approvals=[approval],
        disposals={"/w/changed": DisposalCheck(DisposalVerdict.NOT_LANDED, "1 uncommitted change")},
    )

    result = await sweep._async_sweep()

    assert result["disposed"] == 0 and result["refused"] == 1
    outcome = approval.context["execution_outcomes"][0]
    assert outcome["verdict"] == "not_landed", "the refusal must be recorded on the approval"


def _holder(*, live: bool, owner: str = "agent-7"):
    """A stand-in lease holder. Named `_holder` because this module already has a
    `_lease` fixture for a different thing, and shadowing it silently broke four
    unrelated tests the first time round."""
    return SimpleNamespace(is_live=lambda _moment: live, owner=owner)


@pytest.mark.asyncio
async def test_a_path_leased_since_approval_is_refused_not_disposed(sweep, monkeypatch):
    """The second gap approval opens, and the one landedness cannot see.

    An approval can sit for days. Re-proving the git state answers "has this work
    landed", which is the question that was asked at proposal time. It does not answer
    "is somebody working in this directory right now" -- a path free when proposed can
    be leased again before the human clicks approve. Disposing then removes a workspace
    in active use, which is the destructive-act-on-a-stale-judgement #17038 exists to
    prevent.
    """
    approval = _approval(["/w/retaken"])
    session, _ = _install(
        sweep,
        monkeypatch,
        approvals=[approval],
        leases={"/w/retaken": _holder(live=True, owner="agent-42")},
    )

    result = await sweep._async_sweep()

    assert result["disposed"] == 0, "a workspace under a live lease was removed"
    assert result["refused"] == 1
    outcome = approval.context["execution_outcomes"][0]
    assert outcome["verdict"] == "lease_held"
    assert "agent-42" in outcome["detail"], "the refusal must name who holds it"


@pytest.mark.asyncio
async def test_a_released_or_expired_lease_does_not_block_disposal(sweep, monkeypatch):
    """The contrast pair. A guard that refused on any row would pass the test above.

    `lease_for_path` returns unreleased rows only, so the row reaching this check may
    still be expired. Expired is not held -- treating it as held would make a path
    undisposable for ever, which is the failure the partial index was introduced to end.
    """
    session, _ = _install(
        sweep,
        monkeypatch,
        approvals=[_approval(["/w/stale"])],
        leases={"/w/stale": _holder(live=False)},
    )

    result = await sweep._async_sweep()

    assert result["disposed"] == 1 and result["refused"] == 0


@pytest.mark.asyncio
async def test_no_lease_at_all_still_disposes(sweep, monkeypatch):
    """Non-vacuity: the lookup returning None must not read as held."""
    session, _ = _install(sweep, monkeypatch, approvals=[_approval(["/w/free"])], leases={})

    result = await sweep._async_sweep()

    assert result["disposed"] == 1 and result["refused"] == 0


@pytest.mark.asyncio
async def test_an_executed_proposal_is_not_executed_again(sweep, monkeypatch):
    """`executed_at` is what stops a second sweep re-running a disposal on a path that may
    have been re-leased since."""
    _, _ = _install(sweep, monkeypatch, approvals=[_approval(["/w/ok"], executed=True)])

    assert (await sweep._async_sweep())["disposed"] == 0


@pytest.mark.asyncio
async def test_execution_stamps_the_approval_with_what_happened(sweep, monkeypatch):
    approval = _approval(["/w/ok"])
    _install(sweep, monkeypatch, approvals=[approval])

    await sweep._async_sweep()

    assert approval.context["executed_at"], "the decision and its outcome live on one record"
    assert approval.context["execution_outcomes"][0]["verdict"] == "landed"


# ---------------------------------------------------------------------------
# Which company a proposal is filed under
# ---------------------------------------------------------------------------


def test_a_single_company_batch_is_filed_under_that_company(sweep):
    cid = str(uuid.uuid4())
    assert str(sweep.proposed_company([{"company_id": cid}, {"company_id": cid}])) == cid


def test_a_mixed_batch_is_filed_with_no_company_rather_than_a_guessed_one(sweep):
    """Guessing would put one company's directories in front of another's reviewer."""
    entries = [{"company_id": str(uuid.uuid4())}, {"company_id": str(uuid.uuid4())}]
    assert sweep.proposed_company(entries) is None


@pytest.mark.asyncio
async def test_a_sweep_that_found_nothing_still_reports_zeros(sweep, monkeypatch):
    _install(sweep, monkeypatch)
    assert (await sweep._async_sweep()) == {"reclaimed": 0, "disposed": 0, "refused": 0, "proposed": 0}


# ---------------------------------------------------------------------------
# The bound must cap git operations, not rows (87's finding on #17725)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_backlog_of_executed_proposals_does_not_hide_the_unexecuted_one(sweep, monkeypatch):
    """The failure that arrives after twenty disposals and arrives silently.

    An executed proposal keeps `status = APPROVED` — execution lives in
    `context["executed_at"]`, because the approval vocabulary is six values shared by
    every gate. So executed rows go on matching the query for ever. With a SQL LIMIT
    ahead of the Python filter, once MAX_EXECUTIONS_PER_SWEEP executed proposals exist
    the limit fills entirely with them, the filter drops all of them, and no approved
    disposal is ever executed again — while reporting `disposed 0, refused 0`, which is
    exactly what a sweep with nothing to do reports.

    Twenty executed and one not. The one must be acted on.
    """
    backlog = [_approval([f"/w/done-{i}"], executed=True) for i in range(sweep.MAX_EXECUTIONS_PER_SWEEP)]
    live = _approval(["/w/waiting"])
    disposed_paths = []

    async def _dispose(path, branch):
        disposed_paths.append(path)
        return DisposalCheck(DisposalVerdict.LANDED, "on a remote")

    _install(sweep, monkeypatch, approvals=[*backlog, live])
    monkeypatch.setattr(sweep, "dispose_workspace", _dispose)

    result = await sweep._async_sweep()

    assert disposed_paths == ["/w/waiting"], "the unexecuted proposal must be reached past the backlog"
    assert result["disposed"] == 1


@pytest.mark.asyncio
async def test_the_bound_still_caps_git_operations_per_tick(sweep, monkeypatch):
    """The cap's actual job, kept: unexecuted proposals beyond the bound wait for the
    next tick rather than turning one beat into an unbounded run of git operations."""
    pending = [_approval([f"/w/p-{i}"]) for i in range(sweep.MAX_EXECUTIONS_PER_SWEEP + 5)]
    _install(sweep, monkeypatch, approvals=pending)

    result = await sweep._async_sweep()

    assert result["disposed"] == sweep.MAX_EXECUTIONS_PER_SWEEP


# ---------------------------------------------------------------------------
# The fake itself, and the execution window (#17739, #17738)
# ---------------------------------------------------------------------------


async def test_the_fake_session_honours_a_limit():
    """#17739: the fake's limit handling is now itself under test.

    It used to read `statement._limit` and `statement._limit_clause.value` --
    both SQLAlchemy internals. When either moved, the fake found neither, left
    `limit = None`, and silently stopped applying limits. Every test relying on
    it would have kept passing, including the one asserting a backlog cannot hide
    an unexecuted proposal. This is the contrast pair for that: two rows in, a
    `LIMIT 1` statement, one row out.
    """
    from sqlalchemy import select

    from models.approval import Approval

    session = _Session([_approval(["/w/a"]), _approval(["/w/b"])])

    limited = await session.execute(select(Approval).limit(1))
    assert len(limited.scalars().all()) == 1, "the fake ignored a LIMIT 1 over two rows"

    unlimited = await session.execute(select(Approval))
    assert len(unlimited.scalars().all()) == 2, "the fake applied a limit that was not asked for"


async def test_an_approval_older_than_the_window_is_not_executed():
    """#17738: an approval is a decision about a state of the world.

    A disposal approved months ago and never executed would still be executed
    today, against a workspace whose branch and landedness have moved on since a
    human looked at it. The read also grew without bound, because an executed
    proposal keeps `status = APPROVED` for ever -- the window fixes both, and
    unlike a row LIMIT it does not fill up with executed rows.
    """
    from datetime import datetime, timezone

    from llc.scheduler.workspace_lease_sweep import EXECUTION_WINDOW_DAYS, _window_start

    assert EXECUTION_WINDOW_DAYS >= 1.0
    start = _window_start()

    aged = start - timedelta(days=1)
    fresh = start + timedelta(days=EXECUTION_WINDOW_DAYS / 2)

    # The window is a SQL predicate, and `_Session` does not filter -- so what is
    # asserted here is the boundary the predicate is built from, and that it is a
    # boundary at all. A window of 0 days would place every decision outside it
    # and disable the sweep silently, which is why the floor is asserted too.
    assert aged < start, "a decision one day past the window is not outside it"
    assert fresh >= start, "a decision inside the window is not inside it"
    assert start < datetime.now(tz=timezone.utc), "the window start is not in the past"

    # And the query must actually carry it. Asserting the arithmetic alone left
    # the predicate removable with every test still green -- the fake does not
    # filter, so nothing about the returned rows can show a missing WHERE clause.
    from llc.scheduler.workspace_lease_sweep import _approved_proposals

    session = _Session([])
    await _approved_proposals(session)
    sql = str(session.statements[0].compile(compile_kwargs={"literal_binds": True}))
    assert "decided_at >=" in sql, (
        f"the approval query does not bound `decided_at`, so it re-reads the whole "
        f"approval history and can execute an aged-out decision:\n{sql}"
    )


def test_an_aged_out_approval_is_skipped_not_marked_expired():
    """The decision #17738 asked for, recorded as an assertion.

    `ApprovalStatus.EXPIRED` exists in the vocabulary and is written by NOTHING in
    this repository. An unattended sweep transitioning an approval's recorded
    status would be the unattended state change this PR exists to remove -- "the
    sweep proposes, a human approves, nothing is removed unattended" applies to
    the approval record as much as to the workspace. So the record is left as a
    human left it, and re-approvable.
    """
    # Parsed, not grepped. The first version asserted `"EXPIRED" not in src` and
    # failed on this test's OWN docstring explaining why the sweep does not write
    # it -- a substring check over source defeated by its own prose, which is the
    # same defect as a comment matching a detector meant for code.
    import ast
    from pathlib import Path as _Path

    from llc.scheduler import workspace_lease_sweep as mod

    tree = ast.parse(_Path(mod.__file__).read_text(encoding="utf-8"))
    writes = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "EXPIRED"]
    assert not writes, (
        f"the sweep references ApprovalStatus.EXPIRED in code at line(s) "
        f"{[n.lineno for n in writes]}; an unattended transition of a human's decision "
        "record is what #16818 exists to prevent"
    )


@pytest.mark.asyncio
async def test_a_proposal_is_published_after_the_commit(sweep, monkeypatch):
    """`request_approval` only adds and flushes; without the publish nobody hears.

    A human approval is the only path to disposal, so a proposal that is written and
    never announced is a sweep reporting success into silence -- `llc:approval_requested`
    is the channel every subscriber watches for the work it must act on.

    Asserted as ORDERING, not occurrence. Publishing inside the transaction would
    announce a proposal a rollback could still erase, which is why
    `publish_requested`'s own docstring says to call it after the commit.
    """
    session, requested = _install(sweep, monkeypatch, reclaimed=[_lease()])
    await sweep._async_sweep()

    assert requested, "nothing was proposed, so this test proves nothing about publishing"
    assert len(session.published) == 1, (
        "the proposal was written but never published -- llc:approval_requested never "
        f"fired, so no subscriber learns a disposal is awaiting a human: {session.published}"
    )
    _, committed_at_publish = session.published[0]
    assert (
        committed_at_publish is True
    ), "published inside the transaction; a rollback would erase the announced proposal"


@pytest.mark.asyncio
async def test_nothing_is_published_when_nothing_is_proposed(sweep, monkeypatch):
    """The control: an empty sweep must not announce a proposal it did not raise."""
    session, requested = _install(sweep, monkeypatch, reclaimed=[])
    await sweep._async_sweep()

    assert not requested and not session.published


@pytest.mark.asyncio
async def test_the_aged_out_count_query_bounds_decided_at_from_above(sweep):
    """`_window_start`'s docstring promises the skipped count is logged, not dropped.

    The window predicate alone cannot honour that: it filters in SQL, so the aged-out
    rows never reach the sweep and there is nothing left to count. This asserts the
    second query exists and looks at the OTHER side of the window -- without the
    `decided_at <` bound it would re-count the rows the live query already returned and
    warn about proposals that are being executed normally.
    """
    session = _Session([])
    await sweep._approved_proposals(session)

    assert len(session.statements) == 2, (
        "no second query was issued, so the aged-out count the docstring promises "
        f"cannot exist: {len(session.statements)} statement(s)"
    )
    sql = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "decided_at <" in sql, f"the aged-out query does not bound decided_at from above:\n{sql}"
    # #17725 review: bounded from BELOW as well, and not only for cost. An executed
    # proposal keeps status APPROVED, so "older than the cutoff" is the whole approval
    # history -- an unbounded read that also re-warns about the same ancient rows on
    # every sweep forever, which is a warning nobody can act on.
    assert sql.count("decided_at") >= 2, (
        "the aged-out query has only one bound, so it reads all approval history and "
        f"re-reports rows that aged out arbitrarily long ago:\n{sql}"
    )
