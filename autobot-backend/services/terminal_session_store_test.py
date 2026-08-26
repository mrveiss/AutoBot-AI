# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the Redis-backed terminal session registry (#14961).

Every fixture here uses its own ``fakeredis`` instance -- never the live
Redis (#14961 constraint). Two-worker scenarios use two independent
``fakeredis.FakeRedis`` clients pointed at the *same* ``fakeredis.FakeServer``,
which is the fakeredis idiom for "two processes talking to one real Redis":
each client is a distinct connection/object, exactly like two uvicorn
workers, but they share the same backing store, exactly like one Redis
deployment.
"""

from enum import Enum

import fakeredis
import pytest

from api.schemas_terminal import SecurityLevel
from services.terminal_session_store import SessionConfigStore, TerminalSessionStoreWriteError


def _client_pair() -> tuple:
    """Two independent fakeredis clients sharing one backing server."""
    server = fakeredis.FakeServer()
    return fakeredis.FakeRedis(server=server), fakeredis.FakeRedis(server=server)


def _unavailable_store() -> SessionConfigStore:
    """A store whose Redis is unreachable, without touching the real client factory."""
    store = SessionConfigStore()
    store._client = lambda: None  # simulate a Redis outage
    return store


class TestCrossWorkerResolution:
    """#14961 AC 3: a session created on one worker resolves from another."""

    def test_session_created_on_one_worker_resolves_from_another(self):
        client_a, client_b = _client_pair()
        store_worker_a = SessionConfigStore(redis_client=client_a)
        store_worker_b = SessionConfigStore(redis_client=client_b)  # fresh instance, own client

        session_id = "session-created-on-a"
        config = {"owner": "alice", "security_level": "standard", "conversation_id": "conv-1"}
        store_worker_a[session_id] = config

        resolved = store_worker_b.get(session_id)

        assert resolved is not None, "worker B could not see worker A's session -- registry is not actually shared"
        assert resolved["owner"] == "alice"
        assert resolved["conversation_id"] == "conv-1"
        # Not the same dict/object worker A wrote -- proves this round-tripped
        # through the shared store rather than through any in-process cache.
        assert resolved is not config

    def test_two_fresh_terminal_managers_share_state_through_redis(self, monkeypatch):
        """Same scenario, through TerminalManager's own default construction (#14961).

        Deliberately does NOT assign `.session_configs` after construction --
        that would only re-prove the store-level test above. This patches the
        client factory `TerminalManager.__init__` -> `SessionConfigStore()`
        resolves lazily, so it exercises the actual production wiring: two
        independently-constructed `TerminalManager()` instances (one per
        simulated worker) end up sharing state because the *default*
        construction is Redis-backed. Reverting `TerminalManager.__init__` to
        `self.session_configs = {}` (the pre-#14961 shape) fails this test,
        because a plain dict has no way to honour the patched factory at all.
        """
        from api.terminal_handlers import TerminalManager

        server = fakeredis.FakeServer()
        # A fresh fakeredis client per call, all sharing one server -- exactly
        # what `get_redis_client(database="sessions")` gives two different
        # workers talking to one real Redis: distinct connections, one store.
        monkeypatch.setattr(
            "services.terminal_session_store.get_redis_client",
            lambda **_kwargs: fakeredis.FakeRedis(server=server),
        )

        manager_worker_a = TerminalManager()
        manager_worker_b = TerminalManager()

        session_id = "session-via-manager-a"
        manager_worker_a.session_configs[session_id] = {"owner": "bob", "security_level": "elevated"}

        resolved = manager_worker_b.session_configs.get(session_id)

        assert resolved is not None, "worker B's default-constructed session_configs did not see worker A's write"
        assert resolved["owner"] == "bob"


class TestUnknownSessionRefused:
    """#14961 AC: an unknown session_id must still resolve to nothing, not defaults."""

    def test_unknown_session_id_returns_none(self):
        store = SessionConfigStore(redis_client=fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        assert store.get("never-created") is None
        assert "never-created" not in store

    def test_unknown_session_id_raises_keyerror_on_subscript(self):
        store = SessionConfigStore(redis_client=fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        with pytest.raises(KeyError):
            _ = store["never-created"]

    def test_deleting_an_unknown_session_does_not_raise(self):
        store = SessionConfigStore(redis_client=fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        del store["never-created"]  # idempotent, matches the call sites' guard-then-delete usage


class TestRedisUnavailableFailsClosed:
    """#14961: authorization-adjacent lookup fails closed, not open, on a Redis outage."""

    def test_get_returns_default_when_redis_is_unreachable(self):
        store = _unavailable_store()
        assert store.get("any-session-id") is None
        assert store.get("any-session-id", "sentinel-default") == "sentinel-default"

    def test_contains_is_false_when_redis_is_unreachable(self):
        store = _unavailable_store()
        assert "any-session-id" not in store

    def test_write_raises_when_redis_is_unreachable(self):
        """A create that cannot be shared must not silently go process-local (#14961)."""
        store = _unavailable_store()
        with pytest.raises(TerminalSessionStoreWriteError):
            store["any-session-id"] = {"owner": "alice"}

    def test_items_yields_nothing_when_redis_is_unreachable_not_an_error(self):
        store = _unavailable_store()
        assert list(store.items()) == []


class TestSecurityLevelRoundTrip:
    """The one non-JSON-native value the old in-process dict tolerated (#14961)."""

    def test_security_level_enum_round_trips_as_its_value(self):
        store = SessionConfigStore(redis_client=fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        store["s1"] = {"security_level": SecurityLevel.ELEVATED}

        stored = store.get("s1")

        assert isinstance(stored["security_level"], str), "must be JSON-native after the round trip, not an Enum"
        assert stored["security_level"] == "elevated"
        # Round-trips back into the enum the same way _init_terminal_handler does.
        assert SecurityLevel(stored["security_level"]) is SecurityLevel.ELEVATED
        assert not isinstance(stored["security_level"], Enum)


class TestItemsEnumeration:
    """Non-vacuity: an enumeration test must prove something was actually found."""

    def test_items_finds_every_stored_session(self):
        client = fakeredis.FakeRedis(server=fakeredis.FakeServer())
        store = SessionConfigStore(redis_client=client)
        expected_ids = {"s1", "s2", "s3"}
        for session_id in expected_ids:
            store[session_id] = {"owner": session_id}

        found = dict(store.items())

        assert found, "items() found nothing -- an empty enumeration must fail this test, not pass it"
        assert set(found.keys()) == expected_ids
        assert all(found[sid]["owner"] == sid for sid in expected_ids)

    def test_items_is_genuinely_empty_for_a_fresh_store(self):
        store = SessionConfigStore(redis_client=fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        assert list(store.items()) == []


class TestPopAndDelete:
    def test_pop_removes_and_returns_the_config(self):
        store = SessionConfigStore(redis_client=fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        store["s1"] = {"owner": "alice"}

        popped = store.pop("s1", None)

        assert popped is not None
        assert popped["owner"] == "alice"
        assert "s1" not in store

    def test_pop_returns_default_for_unknown_session(self):
        store = SessionConfigStore(redis_client=fakeredis.FakeRedis(server=fakeredis.FakeServer()))
        assert store.pop("never-created", "the-default") == "the-default"


class TestTTLApplied:
    def test_write_sets_a_positive_ttl(self):
        client = fakeredis.FakeRedis(server=fakeredis.FakeServer())
        store = SessionConfigStore(redis_client=client)
        store["s1"] = {"owner": "alice"}

        ttl = client.ttl(store._key("s1"))

        assert ttl > 0, "a session config with no TTL would accumulate in Redis forever"
