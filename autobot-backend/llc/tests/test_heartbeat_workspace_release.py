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
        from llc.scheduler.run_workspace import release_workspace_best_effort

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        run_id = uuid.uuid4()

        with patch("llc.scheduler.run_workspace.release_run_workspace", new=AsyncMock()) as released:
            await release_workspace_best_effort(lambda: session, run_id, "rate_limited")

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
        from llc.scheduler.run_workspace import release_workspace_best_effort

        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "llc.scheduler.run_workspace.release_run_workspace",
            new=AsyncMock(side_effect=RuntimeError("db gone")),
        ):
            await release_workspace_best_effort(lambda: session, uuid.uuid4(), "failed")

    @pytest.mark.asyncio
    async def test_the_failed_early_exit_actually_releases(self):
        """Drives the exit rather than reading the source (#17725 review).

        The first early return is reached when marking the run RUNNING raises. A source
        count cannot tell that this path releases; running it can.
        """
        from llc.scheduler.heartbeat_scheduler import HeartbeatScheduler

        run_id = uuid.uuid4()
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.execute = AsyncMock(side_effect=RuntimeError("cannot mark RUNNING"))

        scheduler = HeartbeatScheduler()
        with (
            patch("llc.scheduler.heartbeat_scheduler.get_async_session_factory", return_value=lambda: session),
            patch("llc.scheduler.heartbeat_scheduler.release_workspace_best_effort", new=AsyncMock()) as released,
        ):
            await scheduler._run_adapter({"agent_id": str(uuid.uuid4())}, run_id, {})

        released.assert_awaited_once()
        assert released.await_args[0][1] == run_id
        assert released.await_args[0][2] == "failed", "the FAILED early exit must say so on the release"

    def test_every_return_in_run_adapter_is_preceded_by_a_release(self):
        """Structural, and unlike a reference count it can FAIL (#17725 review).

        `body.count("_release_workspace") == 3` was the previous form. It asserted that
        three release calls exist, not that every exit has one: add a fourth early
        `return` with no release and the count is still three, so the assertion passes
        and the regression it exists to catch goes through.

        This walks each statement list instead and requires a release to appear BEFORE
        the return in that same block, so a new unreleased exit fails by construction
        rather than by someone remembering to update a number.
        """
        import ast
        import inspect

        from llc.scheduler import heartbeat_scheduler as mod

        tree = ast.parse(inspect.getsource(mod.HeartbeatScheduler._run_adapter).lstrip())
        func = tree.body[0]

        def _is_release(node: ast.AST) -> bool:
            """``await release_workspace_best_effort(...)`` as a bare statement."""
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Await):
                return False
            call = node.value.value
            return (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "release_workspace_best_effort"
            )

        unreleased = []
        for parent in ast.walk(func):
            for field in ("body", "orelse", "finalbody"):
                block = getattr(parent, field, None)
                if not isinstance(block, list):
                    continue
                for index, stmt in enumerate(block):
                    if isinstance(stmt, ast.Return) and not any(_is_release(s) for s in block[:index]):
                        unreleased.append(stmt.lineno)

        assert not unreleased, (
            "every early return in _run_adapter must hand the workspace back; these "
            f"return(s) have no release before them in their own block: {unreleased}. "
            "If you added an exit, add the release too."
        )
