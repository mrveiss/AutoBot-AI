# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``FakeAsyncSession`` mirrors the installed ``AsyncSession`` and its opt-ins work (#18883)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import InvalidRequestError, MultipleResultsFound, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from testkit.fake_async_session import FakeAsyncSession, FakeResult, ResultsExhausted

REQUIRED_METHODS = (
    "add add_all flush commit rollback close refresh execute scalar scalars get delete merge "
    "expunge begin begin_nested __aenter__ __aexit__"
).split()


def _shape(func: object) -> list[tuple[str, object]]:
    return [(p.name, p.kind) for p in inspect.signature(func).parameters.values()]


def test_the_method_set_covers_the_documented_surface() -> None:
    missing = [n for n in REQUIRED_METHODS if not callable(getattr(FakeAsyncSession, n, None))]
    assert not missing, f"FakeAsyncSession lacks {missing}"


@pytest.mark.parametrize("name", REQUIRED_METHODS)
def test_signature_parity_with_the_real_session(name: str) -> None:
    fake, real = getattr(FakeAsyncSession, name), getattr(AsyncSession, name)
    assert _shape(fake) == _shape(real), name
    assert inspect.iscoroutinefunction(fake) == inspect.iscoroutinefunction(real), name


def test_every_public_method_the_real_session_shares_is_checked() -> None:
    """A new fake method that the real session also has must join the parity list."""
    shared = {
        n
        for n, v in vars(FakeAsyncSession).items()
        if callable(v) and (not n.startswith("_") or n in ("__aenter__", "__aexit__")) and hasattr(AsyncSession, n)
    }
    assert shared <= set(REQUIRED_METHODS), sorted(shared - set(REQUIRED_METHODS))


@pytest.mark.asyncio
async def test_recording_is_always_on() -> None:
    s = FakeAsyncSession()
    obj = object.__new__(type("M", (), {}))
    s.add(obj)
    await s.execute("stmt")
    await s.flush()
    await s.refresh(obj)
    await s.delete(obj)
    await s.rollback()
    await s.commit()
    assert (s.added, s.statements, s.refreshed, s.deleted) == ([obj], ["stmt"], [obj], [obj])
    assert (s.flushes, s.rollbacks, s.commits, s.committed) == (2, 1, 1, True)


@pytest.mark.asyncio
async def test_assign_ids_numbers_new_objects_on_flush_and_commit() -> None:
    class M:
        id = None

    a, b = M(), M()
    s = FakeAsyncSession(assign_ids=True)
    s.add_all([a, b])
    assert a.id is None
    await s.commit()
    assert (a.id, b.id) == (1, 2)
    assert FakeAsyncSession().added == []


@pytest.mark.asyncio
async def test_assign_ids_accepts_a_factory_for_non_integer_keys() -> None:
    class M:
        id = None

    a = M()
    s = FakeAsyncSession(assign_ids=lambda: "uuid-1")
    s.add(a)
    await s.flush()
    assert a.id == "uuid-1"


@pytest.mark.asyncio
async def test_results_queue_then_default_result() -> None:
    s = FakeAsyncSession(results=[FakeResult(["a"]), ["b"], lambda stmt: [stmt]], default_result=["z"])
    assert (await s.execute("q1")).all() == ["a"]
    assert (await s.execute("q2")).all() == ["b"]
    assert (await s.execute("q3")).all() == ["q3"]
    assert (await s.execute("q4")).all() == ["z"]
    assert await s.scalar("q5") == "z"
    assert (await s.scalars("q6")).all() == ["z"]
    assert (await FakeAsyncSession().execute("q")).all() == []


@pytest.mark.asyncio
async def test_a_queued_exception_is_raised() -> None:
    s = FakeAsyncSession(results=[RuntimeError("db down")])
    with pytest.raises(RuntimeError, match="db down"):
        await s.execute("q")


@pytest.mark.asyncio
async def test_rows_is_the_identity_map_for_get_and_add_registers() -> None:
    class M:
        def __init__(self, id):
            self.id = id

    seen = M(7)
    s = FakeAsyncSession(rows={(M, 7): seen})
    assert await s.get(M, 7) is seen
    assert await s.get(M, 8) is None
    fresh = M(9)
    s.add(fresh)
    assert await s.get(M, 9) is None  # pending: a real session.get does not see it yet
    await s.flush()
    assert await s.get(M, 9) is fresh
    await s.delete(fresh)
    assert await s.get(M, 9) is fresh  # delete is deferred to the flush
    await s.flush()
    assert await s.get(M, 9) is None


@pytest.mark.asyncio
async def test_on_get_answers_what_the_identity_map_does_not_hold() -> None:
    s = FakeAsyncSession(on_get=lambda entity, ident: (entity, ident))
    assert await s.get(int, 3) == (int, 3)


@pytest.mark.asyncio
async def test_commit_error_as_an_exception_or_a_callable_of_the_attempt_number() -> None:
    always = FakeAsyncSession(commit_error=ValueError("boom"))
    with pytest.raises(ValueError):
        await always.commit()
    assert always.commits == 1 and not always.committed

    second = FakeAsyncSession(commit_error=lambda n: RuntimeError("n2") if n == 2 else None)
    await second.commit()
    with pytest.raises(RuntimeError):
        await second.commit()
    await second.commit()
    assert second.commits == 3 and second.committed


@pytest.mark.asyncio
async def test_on_refresh_is_called_with_the_instance() -> None:
    class M:
        id = None

    seen = []
    s = FakeAsyncSession(on_refresh=seen.append)
    obj = M()
    s.add(obj)
    await s.flush()
    await s.refresh(obj)
    assert seen == [obj]


@pytest.mark.asyncio
async def test_context_managers_and_transactions() -> None:
    async with FakeAsyncSession() as s:
        async with s.begin():
            pass
        async with s.begin_nested() as nested:
            await nested.rollback()
    assert s.closed


def test_fake_result_reads() -> None:
    assert FakeResult([1]).scalar_one() == 1
    assert FakeResult([]).scalar_one_or_none() is None
    assert FakeResult([]).scalar() is None and FakeResult([]).first() is None
    assert FakeResult([1, 2]).first() == 1 and FakeResult([1, 2]).scalars().all() == [1, 2]
    assert list(FakeResult([1, 2])) == [1, 2]
    assert FakeResult([{"a": 1}]).mappings().first() == {"a": 1} and FakeResult([]).mappings().first() is None
    assert FakeResult([1, 2]).mappings().all() == [1, 2] and list(FakeResult([1, 2]).mappings()) == [1, 2]
    with pytest.raises(NoResultFound):
        FakeResult([]).scalar_one()
    with pytest.raises(MultipleResultsFound):
        FakeResult([1, 2]).scalar_one_or_none()


@pytest.mark.asyncio
async def test_a_deleted_instance_is_not_re_registered_by_the_commit() -> None:
    """A real session does not hand back a row that was deleted and committed."""
    model = type("M", (), {})
    obj = model()
    obj.id = 7
    s = FakeAsyncSession()
    s.add(obj)
    await s.commit()
    await s.delete(obj)
    await s.commit()
    assert await s.get(model, 7) is None


@pytest.mark.asyncio
async def test_expunge_is_synchronous_and_drops_the_tracked_row() -> None:
    model = type("M", (), {})
    obj = model()
    obj.id = 3
    s = FakeAsyncSession()
    s.add(obj)
    await s.flush()
    assert await s.get(model, 3) is obj  # tracked first, so the test can't pass if expunge is a no-op
    s.expunge(obj)
    assert await s.get(model, 3) is None


_CUSTOM_KEY = (SimpleNamespace, "autobot-pg-backup")


async def _assert_detached(s: FakeAsyncSession, row: object) -> None:
    """A detached row is gone from the identity map and refresh/delete raise like the real session."""
    assert await s.get(*_CUSTOM_KEY) is None and _CUSTOM_KEY not in s.rows
    with pytest.raises(InvalidRequestError):
        await s.refresh(row)
    with pytest.raises(InvalidRequestError):
        await s.delete(row)


@pytest.mark.asyncio
async def test_delete_then_flush_removes_a_row_seeded_under_a_custom_key() -> None:
    """Removal is by identity: a row seeded via ``rows=`` under a non-``(type, id)`` key still goes."""
    row = SimpleNamespace(name="autobot-pg-backup")
    s = FakeAsyncSession(rows={_CUSTOM_KEY: row})
    assert await s.get(*_CUSTOM_KEY) is row  # seeded first, so a no-op removal can't pass
    await s.delete(row)
    await s.flush()
    await _assert_detached(s, row)


@pytest.mark.asyncio
async def test_expunge_removes_a_row_seeded_under_a_custom_key() -> None:
    row = SimpleNamespace(name="autobot-pg-backup")
    s = FakeAsyncSession(rows={_CUSTOM_KEY: row})
    assert await s.get(*_CUSTOM_KEY) is row
    s.expunge(row)
    await _assert_detached(s, row)


@pytest.mark.asyncio
async def test_rollback_restores_a_custom_key_row_its_flush_deleted() -> None:
    row = SimpleNamespace(name="autobot-pg-backup")
    s = FakeAsyncSession(rows={_CUSTOM_KEY: row})
    await s.delete(row)
    await s.flush()
    await s.rollback()
    assert await s.get(*_CUSTOM_KEY) is row


@pytest.mark.asyncio
async def test_an_expunged_pending_instance_is_not_registered_by_a_later_commit() -> None:
    """add -> expunge -> commit: the instance is transient, so get() must not return it (CodeRabbit, #18933)."""
    model = type("M", (), {})
    obj = model()
    obj.id = 7
    s = FakeAsyncSession()
    s.add(obj)
    s.expunge(obj)
    await s.commit()
    assert await s.get(model, 7) is None
    assert obj in s.added  # the call record is kept; only the pending work is dropped


@pytest.mark.asyncio
async def test_contrast_re_adding_an_expunged_instance_makes_it_pending_again() -> None:
    model = type("M", (), {})
    obj = model()
    obj.id = 8
    s = FakeAsyncSession()
    s.add(obj)
    s.expunge(obj)
    s.add(obj)
    await s.commit()
    assert await s.get(model, 8) is obj


def _model(id_=None):
    obj = type("M", (), {})()
    obj.id = id_
    return obj


@pytest.mark.asyncio
async def test_add_does_not_register_in_rows_until_flush_or_commit() -> None:
    obj = _model(4)
    s = FakeAsyncSession()
    s.add(obj)
    assert s.rows == {} and await s.get(type(obj), 4) is None
    await s.commit()
    assert await s.get(type(obj), 4) is obj


@pytest.mark.asyncio
async def test_rollback_drops_pending_and_unregisters_what_this_transaction_flushed() -> None:
    kept, flushed, pending = _model(1), _model(2), _model(3)
    s = FakeAsyncSession()
    s.add(kept)
    await s.commit()
    s.add(flushed)
    await s.flush()
    s.add(pending)
    await s.rollback()
    model = type(kept)
    assert s.rollbacks == 1
    assert await s.get(model, 1) is kept  # committed earlier: survives
    assert await s.get(model, 2) is None and await s.get(model, 3) is None
    await s.commit()  # the rolled-back pending object is not resurrected by a later commit
    assert await s.get(model, 3) is None


@pytest.mark.asyncio
async def test_rollback_restores_what_this_transaction_deleted() -> None:
    obj = _model(5)
    s = FakeAsyncSession(rows={(type(obj), 5): obj})
    await s.delete(obj)
    await s.flush()
    assert await s.get(type(obj), 5) is None
    await s.rollback()
    assert await s.get(type(obj), 5) is obj


@pytest.mark.asyncio
async def test_begin_commits_on_a_clean_exit_and_rolls_back_on_an_exception() -> None:
    obj = _model(6)
    s = FakeAsyncSession()
    async with s.begin():
        s.add(obj)
    assert (s.commits, s.rollbacks) == (1, 0)
    assert await s.get(type(obj), 6) is obj

    other = _model(7)
    with pytest.raises(RuntimeError, match="boom"):  # contrast: the exception propagates
        async with s.begin():
            s.add(other)
            raise RuntimeError("boom")
    assert (s.commits, s.rollbacks) == (1, 1)
    assert await s.get(type(obj), 7) is None


@pytest.mark.asyncio
async def test_begin_surfaces_a_commit_error_from_its_exit() -> None:
    s = FakeAsyncSession(commit_error=ValueError("boom"))
    with pytest.raises(ValueError):
        async with s.begin():
            pass


@pytest.mark.asyncio
async def test_begin_nested_flushes_on_exit_and_undoes_only_its_own_work_on_error() -> None:
    outer, inner, later = _model(8), _model(9), _model(10)
    s = FakeAsyncSession()
    s.add(outer)
    await s.flush()  # flushed BEFORE the savepoint: the savepoint's rollback must leave it alone
    with pytest.raises(RuntimeError):
        async with s.begin_nested():
            s.add(inner)
            await s.flush()
            raise RuntimeError("savepoint failed")
    assert s.rollbacks == 1 and s.commits == 0
    assert await s.get(type(inner), 9) is None
    assert await s.get(type(outer), 8) is outer
    async with s.begin_nested():
        s.add(later)
    assert await s.get(type(later), 10) is later  # a clean exit flushes; the outer transaction owns the commit
    assert s.commits == 0 and s.rollbacks == 1


@pytest.mark.asyncio
async def test_refresh_and_delete_of_a_never_persisted_object_raise() -> None:
    obj = _model()
    s = FakeAsyncSession(assign_ids=True)
    with pytest.raises(InvalidRequestError):
        await s.refresh(obj)
    s.add(obj)  # pending is not persistent either
    with pytest.raises(InvalidRequestError):
        await s.refresh(obj)
    with pytest.raises(InvalidRequestError):
        await s.delete(obj)
    assert obj.id is None and s.refreshed == [] and s.deleted == []
    await s.flush()
    await s.refresh(obj)
    assert obj.id == 1 and s.refreshed == [obj]


@pytest.mark.asyncio
async def test_objects_loaded_by_execute_get_or_rows_can_be_refreshed_and_deleted() -> None:
    a, b, c = _model(1), _model(2), _model(3)
    s = FakeAsyncSession(results=[[a]], rows={(type(c), 3): c}, on_get=lambda e, i: b)
    await s.execute("q")
    await s.get(type(b), 2)
    for obj in (a, b, c):
        await s.refresh(obj)
        await s.delete(obj)
    assert s.refreshed == [a, b, c] and s.deleted == [a, b, c]


@pytest.mark.asyncio
async def test_strict_raises_when_the_results_queue_is_exhausted() -> None:
    s = FakeAsyncSession(results=[["a"]], default_result=["z"], strict=True)
    assert (await s.execute("q1")).all() == ["a"]
    with pytest.raises(ResultsExhausted):
        await s.execute("q2")
    assert s.statements == ["q1", "q2"]
    # contrast: not strict, the same exhaustion falls back to default_result
    loose = FakeAsyncSession(default_result=["z"])
    assert (await loose.execute("q")).all() == ["z"]


@pytest.mark.asyncio
async def test_scalar_and_scalars_forward_every_kwarg_to_execute() -> None:
    seen: list = []

    class Spy(FakeAsyncSession):
        async def execute(self, statement, params=None, *, execution_options=None, bind_arguments=None, **kw):
            seen.append((params, execution_options, bind_arguments, kw))
            return await super().execute(statement, params, execution_options=execution_options)

    s = Spy(default_result=[1])
    await s.scalar("q", {"p": 1}, execution_options={"e": 1}, bind_arguments={"b": 1}, extra=1)
    await s.scalars("q", {"p": 2}, execution_options={"e": 2}, bind_arguments={"b": 2}, extra=2)
    assert seen == [
        ({"p": 1}, {"e": 1}, {"b": 1}, {"extra": 1}),
        ({"p": 2}, {"e": 2}, {"b": 2}, {"extra": 2}),
    ]


@pytest.mark.asyncio
async def test_outer_pending_work_survives_a_savepoint_rollback() -> None:
    """add(a) -> begin_nested -> flush -> raise: a was flushed before the SAVEPOINT, so it stays (#18933)."""
    model = type("M", (), {})
    a, b = model(), model()
    a.id, b.id = 1, 2
    s = FakeAsyncSession()
    s.add(a)
    with pytest.raises(RuntimeError):
        async with s.begin_nested():
            s.add(b)
            await s.flush()
            raise RuntimeError("savepoint body fails")
    assert await s.get(model, 1) is a
    assert await s.get(model, 2) is None


@pytest.mark.asyncio
async def test_awaiting_begin_nested_starts_a_savepoint_like_a_real_session() -> None:
    """``tx = await session.begin_nested()`` is valid SQLAlchemy; the fake must accept it too (#18955)."""
    model = type("M", (), {})
    a = model()
    a.id = 4
    s = FakeAsyncSession()
    tx = await s.begin_nested()
    s.add(a)
    await tx.rollback()
    assert await s.get(model, 4) is None
    assert s.rollbacks == 1
