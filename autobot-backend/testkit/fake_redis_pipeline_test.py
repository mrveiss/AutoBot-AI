# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The canonical Redis pipeline fake queues, applies on EXEC, and matches redis-py's surface (#18991)."""

import pytest
import redis.asyncio.client as async_client
import redis.client as sync_client

from testkit.fake_redis_pipeline import COMMANDS, FakeAsyncPipeline, FakePipeline, WatchError

_TTL = 9  # an arbitrary expiry the target must receive unchanged


class _Store:
    """Async target: a dict of strings and a record of every call it received."""

    def __init__(self, **strings):
        self.strings = dict(strings)
        self.calls = []

    async def set(self, key, value, ex=None):
        self.calls.append(("set", key, value, ex))
        self.strings[key] = value
        return True

    async def get(self, key):
        return self.strings.get(key)

    async def incrby(self, key, amount):
        self.strings[key] = self.strings.get(key, 0) + amount
        return self.strings[key]


class _SyncStore:
    def __init__(self):
        self.hashes = {"h": {"f": "v"}}

    def hgetall(self, key):
        return self.hashes.get(key, {})

    def get(self, key):
        return self.hashes.get(key)


@pytest.mark.parametrize("pipeline_class", [async_client.Pipeline, sync_client.Pipeline])
def test_every_queued_command_exists_on_the_real_pipeline(pipeline_class):
    # The commands are generated `*args, **kwargs` methods, so parameter names are NOT compared with
    # redis-py's signatures: the fake declares none to compare. Arity and names are the target's to enforce.
    assert COMMANDS, "an empty command set would assert nothing"
    assert [name for name in sorted(COMMANDS) if not hasattr(pipeline_class, name)] == []
    assert not hasattr(pipeline_class, "bogus_cmd"), "contrast: the check can fail on a name redis-py lacks"


@pytest.mark.parametrize("fake_class", [FakeAsyncPipeline, FakePipeline])
def test_the_public_surface_exists_on_the_real_pipeline(fake_class):
    real = async_client.Pipeline if fake_class is FakeAsyncPipeline else sync_client.Pipeline
    surface = {name for name in dir(fake_class()) if not name.startswith("_")} - {"commands", "executed"}
    assert surface, "an empty surface would assert nothing"
    assert [name for name in sorted(surface) if not hasattr(real, name)] == []


def test_a_command_redis_py_does_not_have_is_not_silently_accepted():
    with pytest.raises(AttributeError):
        FakeAsyncPipeline().not_a_redis_command("k")


@pytest.mark.asyncio
async def test_commands_queue_and_apply_in_order_on_execute():
    store = _Store()
    pipe = FakeAsyncPipeline(store)

    assert pipe.incrby("n", 2) is pipe
    pipe.incrby("n", 3).set("k", "v", ex=_TTL)
    assert store.strings == {}, "nothing applies before EXEC"
    assert pipe.commands == [("incrby", "n", 2), ("incrby", "n", 3), ("set", "k", "v")]

    assert await pipe.execute() == [2, 5, True]
    assert store.calls == [("set", "k", "v", _TTL)]
    assert pipe.commands == [] and pipe.executed == [[("incrby", "n", 2), ("incrby", "n", 3), ("set", "k", "v")]]


@pytest.mark.asyncio
async def test_async_commands_are_awaitable_and_the_context_manager_resets():
    store = _Store()
    async with FakeAsyncPipeline(store) as pipe:
        assert await pipe.incrby("n", 1) is pipe
        pipe.incrby("n", 1)
    assert pipe.commands == [] and store.strings == {}, "leaving without EXEC discards the queue"


@pytest.mark.asyncio
async def test_without_a_target_commands_are_recorded_and_each_result_is_true():
    pipe = FakeAsyncPipeline()
    pipe.sadd("s", "a").srem("s", "b")
    assert await pipe.execute() == [True, True]
    assert pipe.executed == [[("sadd", "s", "a"), ("srem", "s", "b")]]


@pytest.mark.asyncio
async def test_after_watch_a_command_runs_immediately_until_multi():
    store = _Store(k="old")
    pipe = FakeAsyncPipeline(store)

    await pipe.watch("k")
    assert await pipe.get("k") == "old"
    pipe.multi()
    pipe.set("k", "new")
    assert store.strings["k"] == "old"
    assert await pipe.execute() == [True]
    assert store.strings["k"] == "new"


@pytest.mark.asyncio
async def test_without_watch_a_get_is_queued_not_run():
    store = _Store(k="old")
    pipe = FakeAsyncPipeline(store)
    pipe.get("k")
    assert pipe.commands == [("get", "k")]
    assert await pipe.execute() == ["old"]


@pytest.mark.asyncio
async def test_execute_errors_fail_one_exec_each_then_a_retry_applies():
    store = _Store()
    pipe = FakeAsyncPipeline(store, execute_errors=[WatchError()])
    pipe.set("k", "v")
    with pytest.raises(WatchError):
        await pipe.execute()
    assert store.strings == {} and pipe.executed == [], "a failed EXEC applies nothing and is not recorded"
    pipe.set("k", "v")
    assert await pipe.execute() == [True]


@pytest.mark.asyncio
async def test_execute_error_fails_every_exec():
    pipe = FakeAsyncPipeline(_Store(), execute_error=WatchError())
    for _ in range(2):
        pipe.set("k", "v")
        with pytest.raises(WatchError):
            await pipe.execute()


@pytest.mark.asyncio
async def test_a_command_error_does_not_roll_back_the_rest_of_the_transaction():
    store = _Store()
    pipe = FakeAsyncPipeline(store, command_errors={"incrby": TypeError("WRONGTYPE")})
    pipe.incrby("n", 1).set("k", "v")

    results = await pipe.execute(raise_on_error=False)

    assert isinstance(results[0], TypeError) and results[1] is True
    assert store.strings == {"k": "v"}


@pytest.mark.asyncio
async def test_raise_on_error_raises_after_every_command_ran():
    store = _Store()
    pipe = FakeAsyncPipeline(store, command_errors={"incrby": TypeError("WRONGTYPE")})
    pipe.incrby("n", 1).set("k", "v")
    with pytest.raises(TypeError):
        await pipe.execute()
    assert store.strings == {"k": "v"}


@pytest.mark.asyncio
async def test_a_watched_key_that_changed_raises_watch_error_when_conflicts_are_detected():
    store = _Store(k="1")
    pipe = FakeAsyncPipeline(store, detect_watch_conflicts=True)
    await pipe.watch("k")
    store.strings["k"] = "2"
    pipe.multi()
    pipe.set("k", "3")
    with pytest.raises(WatchError):
        await pipe.execute()
    assert store.strings["k"] == "2"


@pytest.mark.asyncio
async def test_an_unchanged_watched_key_executes_and_conflicts_are_off_by_default():
    store = _Store(k="1")
    pipe = FakeAsyncPipeline(store, detect_watch_conflicts=True)
    await pipe.watch("k")
    pipe.multi()
    pipe.set("k", "3")
    assert await pipe.execute() == [True]

    lax = FakeAsyncPipeline(store)
    await lax.watch("k")
    store.strings["k"] = "9"
    lax.multi()
    lax.set("k", "4")
    assert await lax.execute() == [True], "contrast: opt-in only"


@pytest.mark.asyncio
async def test_unwatch_and_reset_drop_the_watch():
    pipe = FakeAsyncPipeline(_Store(k="1"))
    await pipe.watch("k")
    await pipe.unwatch()
    pipe.get("k")
    assert pipe.commands == [("get", "k")], "after unwatch a command queues again"


@pytest.mark.asyncio
async def test_json_get_queues_on_the_pipeline_and_resolves_through_the_target():
    class _Redis:
        def json(self):
            return self

        async def get(self, key):
            return {"id": key}

    pipe = FakeAsyncPipeline(_Redis())
    pipe.json().get("doc:1")
    assert pipe.commands == [("json.get", "doc:1")]
    assert await pipe.execute() == [{"id": "doc:1"}]


def test_the_sync_pipeline_returns_the_result_list_without_awaiting():
    pipe = FakePipeline(_SyncStore())
    pipe.hgetall("h").hgetall("missing")
    assert pipe.execute() == [{"f": "v"}, {}]
    with FakePipeline(_SyncStore()) as ctx:
        ctx.get("h")
    assert ctx.commands == []


def test_the_sync_pipeline_raises_an_injected_watch_error():
    pipe = FakePipeline(_SyncStore(), execute_errors=[WatchError()])
    pipe.get("h")
    with pytest.raises(WatchError):
        pipe.execute()
    pipe.get("h")
    assert pipe.execute() == [{"f": "v"}]


@pytest.mark.asyncio
async def test_an_empty_queue_returns_an_empty_list_and_injects_nothing():
    pipe = FakeAsyncPipeline(_Store(), execute_errors=[WatchError()], execute_error=WatchError())
    assert await pipe.execute() == []
    assert pipe.executed == []
    pipe.set("k", "v")
    with pytest.raises(WatchError):
        await pipe.execute()  # contrast: with a queued command the same pipeline does inject


@pytest.mark.asyncio
async def test_without_a_transaction_there_is_no_watch_error_or_conflict():
    store = _Store(k="1")
    injected = FakeAsyncPipeline(store, transaction=False, execute_error=WatchError())
    injected.set("a", "v")
    assert await injected.execute() == [True]

    conflict = FakeAsyncPipeline(store, transaction=False, detect_watch_conflicts=True)
    await conflict.watch("k")
    store.strings["k"] = "2"
    conflict.multi()
    conflict.set("k", "3")
    assert await conflict.execute() == [True]

    dead = FakeAsyncPipeline(store, transaction=False, execute_error=ConnectionError("down"))
    dead.set("a", "v")
    with pytest.raises(ConnectionError):
        await dead.execute()  # a non-WATCH failure still fires


@pytest.mark.asyncio
async def test_command_errors_still_apply_without_a_transaction():
    pipe = FakeAsyncPipeline(_Store(), transaction=False, command_errors={"incrby": TypeError("WRONGTYPE")})
    pipe.incrby("n", 1)
    assert isinstance((await pipe.execute(raise_on_error=False))[0], TypeError)


def test_the_sync_pipeline_honours_the_empty_queue_and_transaction_rules():
    assert FakePipeline(_SyncStore(), execute_error=WatchError()).execute() == []
    pipe = FakePipeline(_SyncStore(), transaction=False, execute_error=WatchError())
    pipe.get("h")
    assert pipe.execute() == [{"f": "v"}]
