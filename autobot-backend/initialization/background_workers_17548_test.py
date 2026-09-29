# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The vector reconciler is actually started, and says so when it is not (#17548).

The defect this closes is not a broken loop — the loop was complete and correct. It had
no caller, which reads as working code in every way except the one that matters. So the
assertion that counts is *a task was created*, and the second one that counts is that a
refusal to start is loud rather than silent.
"""

import asyncio
from types import SimpleNamespace

import pytest

from initialization import background_workers as bw


class _App:
    def __init__(self, kb=None):
        self.state = SimpleNamespace()
        if kb is not None:
            self.state.knowledge_base = kb


class _Vectorizer:
    def __init__(self):
        self.called_with = None

    async def periodic_check(self, kb):
        self.called_with = kb
        await asyncio.sleep(3600)  # a real one never returns; this must not block the test


@pytest.mark.asyncio
async def test_the_reconciler_task_is_created_at_startup(monkeypatch):
    """AC3, and the whole point: a loop nobody starts is the bug.

    Mutation-checked — delete the `create_task` call in `start_vector_reconciler` and only
    this test fails.
    """
    import background_vectorization

    vectorizer = _Vectorizer()

    monkeypatch.setattr(background_vectorization, "get_background_vectorizer", lambda: vectorizer)

    app = _App(kb=object())
    await bw.start_vector_reconciler(app)

    task = getattr(app.state, "vector_reconciler_task", None)
    assert task is not None, "no reconciler task was created"
    assert isinstance(task, asyncio.Task)
    await asyncio.sleep(0)  # let it reach the first await
    assert vectorizer.called_with is app.state.knowledge_base, "the task must run against the app's KB"

    task.cancel()


@pytest.mark.asyncio
async def test_the_task_is_kept_on_app_state_not_dropped(monkeypatch):
    """A task nobody holds a reference to can be collected mid-flight, and the symptom is
    a reconciler that stops without an error. Holding it is not bookkeeping."""
    import background_vectorization

    vectorizer = _Vectorizer()
    monkeypatch.setattr(background_vectorization, "get_background_vectorizer", lambda: vectorizer)
    app = _App(kb=object())

    await bw.start_vector_reconciler(app)

    assert app.state.vector_reconciler_task is not None
    app.state.vector_reconciler_task.cancel()


@pytest.mark.asyncio
async def test_no_knowledge_base_refuses_loudly_and_creates_nothing(caplog):
    """The failure mode this must never have: a task that exists and reconciles nothing.

    Without a KB there is nothing to reconcile against, so starting anyway would log
    failures for ever and still look alive.
    """
    app = _App(kb=None)

    with caplog.at_level("WARNING"):
        await bw.start_vector_reconciler(app)

    assert not hasattr(app.state, "vector_reconciler_task")
    assert any("NOT started" in r.getMessage() for r in caplog.records), "a refusal must be visible"


@pytest.mark.asyncio
async def test_a_failing_start_does_not_take_the_backend_down(monkeypatch, caplog):
    import background_vectorization

    def _boom():
        raise RuntimeError("no vectorizer today")

    monkeypatch.setattr(background_vectorization, "get_background_vectorizer", _boom)
    app = _App(kb=object())

    with caplog.at_level("WARNING"):
        await bw.start_vector_reconciler(app)  # must not raise

    assert any("failed to start" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# The owner's second constraint: a cycle that found nothing must still be visible
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_cycle_is_recorded_even_when_there_is_nothing_to_do(monkeypatch, caplog):
    """ "Found nothing" and "never ran" must not look the same (#17548, #17726).

    This is the defect one level down: the missing caller went unnoticed for months
    because a reconciler that only logs when it finds work is silent in exactly the
    state you would want to detect. A cycle that skips still writes `last_check_at`,
    still increments the counter, and still says why.
    """
    from background_vectorization import BackgroundVectorizer

    v = BackgroundVectorizer()
    v.check_interval = 0
    v.is_running = True  # force the skip path -- nothing to do this cycle

    async def _stop_after_one(_seconds):
        if v._checks_run >= 1:
            raise asyncio.CancelledError
        return None

    monkeypatch.setattr(asyncio, "sleep", _stop_after_one)

    with caplog.at_level("INFO"):
        with pytest.raises(asyncio.CancelledError):
            await v.periodic_check(object())

    assert v._checks_run == 1, "the cycle must be counted even though it did nothing"
    assert v.last_check_at is not None, "the cycle must leave a timestamp"
    assert any("skipped" in r.getMessage() for r in caplog.records), "the skip must say why"


def test_the_interval_is_env_backed_not_a_literal(monkeypatch):
    """AC2. A literal in __init__ cannot be tuned per deployment, which is why it was one."""
    import importlib

    import background_vectorization

    monkeypatch.setenv("AUTOBOT_KB_VECTORIZE_CHECK_INTERVAL_SECONDS", "45")
    reloaded = importlib.reload(background_vectorization)
    try:
        assert reloaded.CHECK_INTERVAL_SECONDS == 45
        assert reloaded.BackgroundVectorizer().check_interval == 45, "the instance must use the constant"
    finally:
        monkeypatch.delenv("AUTOBOT_KB_VECTORIZE_CHECK_INTERVAL_SECONDS", raising=False)
        importlib.reload(background_vectorization)


def test_the_interval_is_floored_so_a_misconfiguration_cannot_busy_loop(monkeypatch):
    import importlib

    import background_vectorization

    monkeypatch.setenv("AUTOBOT_KB_VECTORIZE_CHECK_INTERVAL_SECONDS", "0")
    reloaded = importlib.reload(background_vectorization)
    try:
        assert reloaded.CHECK_INTERVAL_SECONDS >= 30
    finally:
        monkeypatch.delenv("AUTOBOT_KB_VECTORIZE_CHECK_INTERVAL_SECONDS", raising=False)
        importlib.reload(background_vectorization)
