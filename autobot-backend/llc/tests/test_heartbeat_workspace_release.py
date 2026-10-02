# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Early exits in `_run_adapter` must hand the workspace back (#16818, #17725 review).

Split out of `test_heartbeat_scheduler.py`, which sits at its recorded size ceiling of
1075 lines (#14236, #5060): a grandfathered file may not grow, so these tests had to
live somewhere rather than be dropped. The subject is narrower than that file's anyway
-- workspace release on the paths that never reach `_finish_run`.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


class TestEarlyExitsReleaseTheWorkspace:
    """#17725 review: three endings never reached `_finish_run`, the only caller of
    `release_run_workspace`.

    `_finish_run`'s docstring claimed releasing there "cannot miss the failure paths".
    It missed three: the early FAILED path when marking a run RUNNING fails, and the
    rate-limited and quota-exhausted returns. A leaked lease is recovered by the
    expiry sweep, so the symptom is a workspace unusable until its deadline and a
    retry whose acquire fails against a lease nobody is using -- the slow version of
    the bug #16818 is about.
    """

    @pytest.mark.asyncio
    async def test_release_commits_the_handback(self):
        from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        run_id = uuid.uuid4()

        with patch("llc.scheduler.heartbeat_scheduler.release_run_workspace", new=AsyncMock()) as released:
            await HeartbeatScheduler()._release_workspace(lambda: session, run_id, "rate_limited")

        released.assert_awaited_once()
        assert released.await_args[0][1] == run_id
        assert released.await_args[0][2] == "rate_limited", "the status is recorded on the release reason"
        assert session.commit.await_count == 1, "an uncommitted release hands nothing back"

    @pytest.mark.asyncio
    async def test_a_failing_release_does_not_raise(self):
        """The run has already ended and its status is already written.

        Turning a recorded outcome into an unhandled exception would be worse than the
        leak: the sweep recovers a leak, nothing recovers a lost status write.
        """
        from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "llc.scheduler.heartbeat_scheduler.release_run_workspace",
            new=AsyncMock(side_effect=RuntimeError("db gone")),
        ):
            await HeartbeatScheduler()._release_workspace(lambda: session, uuid.uuid4(), "failed")

    @pytest.mark.asyncio
    async def test_every_early_return_in_run_adapter_releases(self):
        """The contrast that matters: it is the EARLY exits, not just the normal one.

        Asserted against the source rather than by driving three dispatch failures,
        because the thing that regresses is someone adding a fourth `return` without a
        release -- and no `finally` covers this path.
        """
        import inspect

        from llc.scheduler import heartbeat_scheduler as mod

        body = inspect.getsource(mod.HeartbeatScheduler._run_adapter)
        assert body.count("_release_workspace") == 3, (
            "every early return in _run_adapter must hand the workspace back; "
            f"found {body.count('_release_workspace')} release call(s). "
            "If you added an exit, add the release too."
        )
        assert "_finish_run" in body, "the normal ending still routes through _finish_run"
