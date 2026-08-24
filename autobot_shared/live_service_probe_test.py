# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The live-service probe must not fail open (#14930).

This guard exists to convert "the service is not running here" into a skip.
The failure mode that would make it worthless is the opposite of a false skip:
a probe that answers "not listening" for *any* problem would turn a genuinely
broken suite into a silently skipped one — the known-red-workflow habit, moved
one layer down. Every test below pins the boundary rather than the happy path.
"""

from __future__ import annotations

import socket
import sys
import types

import pytest

from autobot_shared import live_service_probe
from autobot_shared.live_service_probe import (
    endpoint_is_listening,
    require_live_endpoint,
    reset_probe_cache,
    split_endpoint,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_probe_cache()
    yield
    reset_probe_cache()


@pytest.fixture
def listening_port():
    """A real socket accepting connections, closed when the test ends."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        yield server.getsockname()[1]
    finally:
        server.close()


@pytest.fixture
def closed_port():
    """A port number nothing is bound to: bind, read the port, then release it."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class TestEndpointIsListening:
    def test_true_for_a_socket_that_is_actually_accepting(self, listening_port):
        assert endpoint_is_listening(f"http://127.0.0.1:{listening_port}") is True

    def test_false_when_nothing_is_bound(self, closed_port):
        assert endpoint_is_listening(f"http://127.0.0.1:{closed_port}") is False

    def test_a_non_network_error_propagates_rather_than_reading_as_absent(self, monkeypatch, listening_port):
        """The one assertion that keeps this from becoming a test that cannot fail.

        If ``endpoint_is_listening`` caught ``Exception`` instead of ``OSError``,
        this would return False and every guarded suite would skip forever on a
        bug that has nothing to do with the service being down.
        """

        def _boom(*_args, **_kwargs):
            raise RuntimeError("not a network condition")

        monkeypatch.setattr(live_service_probe.socket, "create_connection", _boom)

        with pytest.raises(RuntimeError, match="not a network condition"):
            endpoint_is_listening(f"http://127.0.0.1:{listening_port}", use_cache=False)

    def test_result_is_cached_per_endpoint(self, monkeypatch, listening_port):
        calls: list[tuple] = []
        real = live_service_probe.socket.create_connection

        def _counting(address, **kwargs):
            calls.append(address)
            return real(address, **kwargs)

        monkeypatch.setattr(live_service_probe.socket, "create_connection", _counting)

        endpoint_is_listening(f"http://127.0.0.1:{listening_port}")
        endpoint_is_listening(f"http://127.0.0.1:{listening_port}")

        assert len(calls) == 1, "the probe reopened a socket it had already answered"

    def test_reset_probe_cache_actually_forgets(self, monkeypatch, listening_port):
        calls: list[tuple] = []
        real = live_service_probe.socket.create_connection

        def _counting(address, **kwargs):
            calls.append(address)
            return real(address, **kwargs)

        monkeypatch.setattr(live_service_probe.socket, "create_connection", _counting)

        endpoint_is_listening(f"http://127.0.0.1:{listening_port}")
        reset_probe_cache()
        endpoint_is_listening(f"http://127.0.0.1:{listening_port}")

        assert len(calls) == 2


class TestSplitEndpoint:
    def test_parses_a_url_with_an_explicit_port(self):
        assert split_endpoint("http://10.0.0.5:8001/api/iac") == ("10.0.0.5", 8001)

    def test_parses_a_bare_host_and_port(self):
        assert split_endpoint("localhost:6379") == ("localhost", 6379)

    def test_falls_back_to_the_scheme_default_port(self):
        assert split_endpoint("https://example.invalid/x") == ("example.invalid", 443)

    def test_explicit_port_argument_wins(self):
        assert split_endpoint("example.invalid", port=9999) == ("example.invalid", 9999)

    @pytest.mark.parametrize("bad", ["", "   ", "http://", "///nope"])
    def test_unparseable_targets_raise_rather_than_guessing(self, bad):
        """A target we cannot parse must never be reported as 'absent'.

        Guessing here would skip a live suite on a typo, which is exactly the
        silent-non-result this whole change exists to remove.
        """
        with pytest.raises(ValueError):
            split_endpoint(bad)

    def test_a_host_with_no_derivable_port_raises(self):
        with pytest.raises(ValueError, match="port"):
            split_endpoint("some-host-with-no-scheme")


class TestRequireLiveEndpoint:
    def test_does_not_skip_when_the_service_is_up(self, listening_port):
        # Reaching the next statement is the assertion: pytest.skip raises.
        require_live_endpoint(f"http://127.0.0.1:{listening_port}", what="a test double")

    def test_skips_with_a_reason_naming_the_service_and_endpoint(self, closed_port):
        with pytest.raises(Exception) as excinfo:
            require_live_endpoint(f"http://127.0.0.1:{closed_port}", what="the AutoBot backend API")

        assert excinfo.typename == "Skipped", f"expected a skip, got {excinfo.typename}"
        message = str(excinfo.value)
        assert "the AutoBot backend API" in message
        assert f"127.0.0.1:{closed_port}" in message

    def test_an_unparseable_target_raises_instead_of_skipping(self):
        with pytest.raises(ValueError):
            require_live_endpoint("", what="nothing")


class TestRedisClientIsStubbed:
    """The stand-in detector must key on module identity, not on a symptom."""

    def test_false_for_the_genuine_module_loaded_from_disk(self, monkeypatch):
        import autobot_shared.redis_client as real

        monkeypatch.setitem(sys.modules, live_service_probe.REDIS_CLIENT_MODULE, real)
        assert real.__file__, "the genuine module must have a __file__ for this check to mean anything"
        assert live_service_probe.redis_client_is_stubbed() is False

    def test_true_for_an_in_memory_stand_in(self, monkeypatch):
        standin = types.ModuleType(live_service_probe.REDIS_CLIENT_MODULE)
        standin.get_redis_client = lambda *a, **k: None
        assert getattr(standin, "__file__", None) is None
        monkeypatch.setitem(sys.modules, live_service_probe.REDIS_CLIENT_MODULE, standin)

        assert live_service_probe.redis_client_is_stubbed() is True

    def test_an_absent_module_is_not_reported_as_stubbed(self, monkeypatch):
        monkeypatch.delitem(sys.modules, live_service_probe.REDIS_CLIENT_MODULE, raising=False)
        assert live_service_probe.redis_client_is_stubbed() is False

    def test_require_real_redis_client_skips_only_under_the_stand_in(self, monkeypatch):
        standin = types.ModuleType(live_service_probe.REDIS_CLIENT_MODULE)
        monkeypatch.setitem(sys.modules, live_service_probe.REDIS_CLIENT_MODULE, standin)

        with pytest.raises(Exception) as excinfo:
            live_service_probe.require_real_redis_client("the knowledge base")

        assert excinfo.typename == "Skipped"
        assert "#14932" in str(excinfo.value), "the skip reason must name the tracking issue"

        import autobot_shared.redis_client as real

        monkeypatch.setitem(sys.modules, live_service_probe.REDIS_CLIENT_MODULE, real)
        # Reaching the next statement is the assertion.
        live_service_probe.require_real_redis_client("the knowledge base")
