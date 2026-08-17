# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`_heartbeat_returned` is executed here, not read (#14344).

Its sibling `reconciler_remediation_outcome_test.py` asserts on the AST: which
value `success` is bound to, that the timings are env-backed. Those rules are
about the *shape* of the fix and they cannot see whether the polling loop works.

Review of this PR made the gap concrete: `_heartbeat_returned` rewritten as
``if False: return True`` / ``return False`` — success permanently unreachable,
every node marching to `exhausted` — satisfies every structural rule, because
both constants still appear as returns. So does a reversed comparison.

These drive the real function with a stateful fake session instead. The module
is loaded from disk rather than imported, because the package conftest stubs the
`services` tree and `import services.reconciler` yields a MagicMock — which
satisfies every structural check while being nothing at all. Its own dependencies
stay stubbed; what is under test is the loop, the comparison and the timeout.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_reconciler():
    """Load services/reconciler.py from disk, past the package conftest's stub.

    `import services.reconciler` returns a MagicMock here: the conftest stubs the
    `services` tree so `api/*` can be imported without the backend. A MagicMock
    satisfies `hasattr`, `callable` and every attribute lookup, so the first
    version of this file imported nothing real and only failed later, on
    `asyncio.run(<MagicMock>)`.

    The module's own dependencies (sqlalchemy, models.database, config) may stay
    stubbed — `select(Node)` is handed straight to the fake session. What must be
    real is this module's code.
    """
    name = "reconciler_under_test"
    spec = importlib.util.spec_from_file_location(name, _SLM_ROOT / "services" / "reconciler.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()


def test_the_real_module_was_loaded_not_a_stub():
    """Guard the guard.

    `hasattr`/`callable` are true of any MagicMock, so they cannot tell a loaded
    module from a stub — that is precisely how the earlier version passed its own
    import check while holding a mock. A coroutine function is something a
    MagicMock is not.
    """
    assert not isinstance(reconciler.ReconcilerService, MagicMock), "ReconcilerService is a stub, not the real class"
    assert inspect.iscoroutinefunction(
        reconciler.ReconcilerService._heartbeat_returned
    ), "_heartbeat_returned is not a coroutine function — the module under test is not the real one"
    assert isinstance(reconciler.REMEDIATION_HEARTBEAT_WAIT_S, int), "the module constants did not evaluate"


class _FakeSessions:
    """Yields a session whose query returns the next scripted node row."""

    def __init__(self, beats):
        self._beats = list(beats)
        self.reads = 0

    @asynccontextmanager
    async def session(self):
        yield SimpleNamespace(execute=self._execute)

    async def _execute(self, _query):
        beat = self._beats[self.reads] if self.reads < len(self._beats) else self._beats[-1]
        self.reads += 1
        row = None if beat is _MISSING else SimpleNamespace(last_heartbeat=beat)
        return SimpleNamespace(scalar_one_or_none=lambda: row)


_MISSING = object()


@contextmanager
def _patched(sessions, wait_s, poll_s):
    """Install the fake session factory and shrink the timings.

    `_heartbeat_returned` does `from services.database import db_service` at call
    time, so the module has to exist then. It is created here when absent rather
    than fetched with `.get()` — a None module would raise during setup, and a
    test that dies before exercising anything is not a failing test, it is an
    absent one.
    """
    name = "services.database"
    created = name not in sys.modules
    if created:
        sys.modules[name] = ModuleType(name)
    db_module = sys.modules[name]
    original = getattr(db_module, "db_service", None)
    db_module.db_service = sessions

    prev_wait = reconciler.REMEDIATION_HEARTBEAT_WAIT_S
    prev_poll = reconciler.REMEDIATION_HEARTBEAT_POLL_S
    reconciler.REMEDIATION_HEARTBEAT_WAIT_S = wait_s
    reconciler.REMEDIATION_HEARTBEAT_POLL_S = poll_s

    # The query object is handed straight to the fake session, so what `select`
    # builds is irrelevant here -- but whether it RAISES is not. Depending on
    # which of sqlalchemy/models.database the conftest happens to stub, a real
    # `select()` over a mock model would error before the loop under test ever
    # runs. Stubbed so these tests turn on the polling logic and nothing else.
    prev_select = reconciler.select
    reconciler.select = lambda *_a, **_k: object()
    try:
        yield
    finally:
        reconciler.select = prev_select
        reconciler.REMEDIATION_HEARTBEAT_WAIT_S = prev_wait
        reconciler.REMEDIATION_HEARTBEAT_POLL_S = prev_poll
        if created:
            del sys.modules[name]
        else:
            db_module.db_service = original


def _run(beats, wait_s=5, poll_s=0, restarted_at=None):
    """Execute the real `_heartbeat_returned` against a scripted heartbeat series."""
    restarted_at = restarted_at or datetime.now(timezone.utc)
    sessions = _FakeSessions(beats)

    with _patched(sessions, wait_s, poll_s):
        node = SimpleNamespace(node_id="node-under-test", last_heartbeat=None)
        result = asyncio.run(reconciler.ReconcilerService._heartbeat_returned(SimpleNamespace(), node, restarted_at))

    return result, sessions.reads


def test_a_heartbeat_after_the_restart_is_success():
    """The whole point: the agent came back."""
    later = datetime.now(timezone.utc) + timedelta(seconds=30)
    verified, reads = _run([None, None, later])

    assert verified is True, "a heartbeat newer than the restart was not counted as success"
    assert reads >= 3, f"returned after {reads} reads — it did not actually poll for the later beat"


def test_no_heartbeat_is_a_failure_and_the_loop_ends():
    """Returning True on timeout is the original bug, restated.

    Success resets the attempt counter, so a verification that cannot fail
    leaves remediation unable to ever reach MAX_REMEDIATION_ATTEMPTS.
    """
    verified, reads = _run([None] * 50, wait_s=0.05)

    assert verified is False, "a node that never heartbeated was reported as remediated"
    assert reads >= 1, "the window expired without the row being read even once"


def test_a_heartbeat_older_than_the_restart_is_not_success():
    """The reversed-comparison mutation.

    A stale timestamp from before the restart is exactly what a node stuck in
    the #14350 401 loop has — it heartbeated successfully once, at enrollment.
    """
    stale = datetime.now(timezone.utc) - timedelta(hours=6)
    verified, _ = _run([stale] * 20, wait_s=0.05)

    assert verified is False, "a heartbeat predating the restart was accepted as proof of recovery"


def test_a_heartbeat_exactly_at_the_restart_is_not_success():
    """`>` not `>=`: the beat has to be strictly after the restart."""
    now = datetime.now(timezone.utc)
    verified, _ = _run([now] * 20, wait_s=0.05, restarted_at=now)

    assert verified is False, "a heartbeat at the exact restart instant was treated as a later one"


def test_a_missing_node_row_is_a_failure_not_a_crash():
    """A deleted or not-yet-visible row must fail the verification quietly.

    An exception here would propagate out of `_remediate_node` and abort the
    whole reconciliation pass for every remaining node.
    """
    verified, _ = _run([_MISSING] * 20, wait_s=0.05)

    assert verified is False, "a missing node row did not fail verification"
