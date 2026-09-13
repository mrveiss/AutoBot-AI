#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Architecture Compliance Tests
=============================

Tests to ensure AutoBot's distributed, role-based architecture (ADR-010) is
properly configured and services resolve to their designated role hosts.

This replaces manual architecture fix scripts with automated validation.
"""

import socket
import sys
import uuid
from pathlib import Path

import pytest
import redis

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# #13286: was `from utils.redis_client import ...`, a module that exists in no tree —
# not under `autobot-infrastructure/shared/`, not under `autobot-backend/`. The import
# died at collection, so this whole module errored out and its 15 checks ran nowhere.
# It went unnoticed because the module carries a marker `ci.yml` deselects and was named
# by no pytest invocation in any workflow until #13286.
#
# `autobot_shared.redis_client` is the canonical accessor CLAUDE.md mandates, and its
# signature is the one the call site below already uses — the old path was a stale alias
# of it, which is why the call needs no change.
from autobot_shared.redis_client import get_redis_client
from config import unified_config_manager
from constants.network_constants import NetworkConstants


class TestServiceDistribution:
    """Test that services are running on correct VMs"""

    def test_redis_on_vm3_only(self):
        """Ensure Redis runs only on VM3 (Redis VM)"""
        redis_config = unified_config_manager.get_redis_config()
        redis_host = redis_config.get("host")

        assert (
            redis_host == NetworkConstants.REDIS_VM_IP
        ), f"Redis must run on VM3 ({NetworkConstants.REDIS_VM_IP}), currently configured for: {redis_host}"

    def test_backend_on_main_machine(self):
        """Ensure backend runs on main machine"""
        backend_config = unified_config_manager.get_backend_config()
        backend_host = backend_config.get("host")

        assert backend_host in [
            NetworkConstants.MAIN_MACHINE_IP,
            "0.0.0.0",
        ], f"Backend must run on main machine ({NetworkConstants.MAIN_MACHINE_IP}), currently configured for: {backend_host}"

    def test_frontend_on_vm1(self):
        """Ensure frontend runs on VM1 (Frontend VM)"""
        services_config = unified_config_manager.get_distributed_services_config()
        frontend_config = services_config.get("frontend", {})
        frontend_host = frontend_config.get("host")

        assert (
            frontend_host == NetworkConstants.FRONTEND_VM_IP
        ), f"Frontend must run on VM1 ({NetworkConstants.FRONTEND_VM_IP}), currently configured for: {frontend_host}"

    def test_npu_worker_on_vm2(self):
        """Ensure NPU worker runs on VM2 (NPU Worker VM)"""
        services_config = unified_config_manager.get_distributed_services_config()
        npu_config = services_config.get("npu_worker", {})
        npu_host = npu_config.get("host")

        assert (
            npu_host == NetworkConstants.NPU_WORKER_VM_IP
        ), f"NPU worker must run on VM2 (NPU Worker VM), currently configured for: {npu_host}"

    def test_ai_stack_on_vm4(self):
        """Ensure AI stack runs on VM4 (AI Stack VM)"""
        services_config = unified_config_manager.get_distributed_services_config()
        ai_config = services_config.get("ai_stack", {})
        ai_host = ai_config.get("host")

        assert (
            ai_host == NetworkConstants.AI_STACK_VM_IP
        ), f"AI stack must run on VM4 (AI Stack VM), currently configured for: {ai_host}"

    # get_distributed_services_config() key -> autobot_shared.ssot_config VMConfig attribute
    _ROLE_TO_SSOT_VM_ATTR = {
        "frontend": "frontend",
        "npu_worker": "npu",
        "redis": "redis",
        "ai_stack": "aistack",
        "browser": "browser",
    }

    def test_service_hosts_resolve_via_ssot_config(self):
        """Every role's configured host matches the SSOT config, whatever that host is.

        #15194: the old assertion pinned the browser role to a specific fixed address
        (``NetworkConstants.BROWSER_VM_IP``), presuming a fixed VM5 exists. AutoBot is
        role-based and count-agnostic (ADR-010): a role's host can be a ``127.0.0.x``
        loopback alias (Docker/single-VM, see VM_ROLES.md), a dedicated VM, or one of
        several machines. What must hold in every deployment is that the value
        ``unified_config_manager`` reports for a role is not an independent literal --
        it is the same value the canonical SSOT config
        (``autobot_shared.ssot_config.config.vm``) declares. Comparing against SSOT
        directly here -- rather than against ``NetworkConstants``, which is itself only
        a ``ConfigRegistry`` proxy in front of the same SSOT -- is what makes this a real
        check rather than a tautology: a stray hardcoded literal, or a stale
        ``ConfigRegistry``/Redis-cache value that has drifted from SSOT, would diverge
        from this comparison and fail here.
        """
        from autobot_shared.ssot_config import config as ssot_config

        services_config = unified_config_manager.get_distributed_services_config()

        for service_key, ssot_attr in self._ROLE_TO_SSOT_VM_ATTR.items():
            host = services_config.get(service_key, {}).get("host")
            expected = str(getattr(ssot_config.vm, ssot_attr))

            assert host, f"'{service_key}' role has no host configured"
            assert host == expected, (
                f"'{service_key}' role host ({host!r}) does not match SSOT "
                f"config.vm.{ssot_attr} ({expected!r}) -- host resolution must go "
                "through SSOT, not a separate literal"
            )


class TestNetworkConfiguration:
    """Test network configuration compliance"""

    def test_distributed_service_hosts_are_resolved(self):
        """Every role's host is a real, resolved value -- loopback included.

        #15194: the old assertion rejected ``localhost``/``127.0.0.1`` outright,
        presuming every role must live on a distinct machine. Docker and single-VM
        deployments correctly bind roles to loopback (or a ``127.0.0.x`` alias --
        see VM_ROLES.md's co-located addressing scheme), so rejecting that failed a
        supported deployment shape rather than catching a bug. What must hold in
        every deployment is that resolution actually happened: each role's host is
        a non-empty, syntactically valid address or hostname -- not ``None``, an
        empty string, or an unresolved template placeholder.
        """
        import ipaddress

        services_config = unified_config_manager.get_distributed_services_config()

        for service_name, service_config in services_config.items():
            if not isinstance(service_config, dict):
                continue

            host = service_config.get("host")
            assert host, f"Service '{service_name}' has no host configured"

            if host == NetworkConstants.LOCALHOST_NAME:
                continue

            try:
                ipaddress.ip_address(host)
                continue
            except ValueError:
                pass

            labels = host.split(".")
            assert labels and all(
                label and all(c.isascii() and (c.isalnum() or c == "-") for c in label) for label in labels
            ), (
                f"Service '{service_name}' host '{host}' is not a valid loopback, "
                "IP address, or hostname"
            )

    def test_backend_binds_to_all_interfaces(self):
        """Ensure backend binds to 0.0.0.0 for network accessibility"""
        backend_config = unified_config_manager.get_backend_config()
        backend_host = backend_config.get("host")

        # Backend should bind to 0.0.0.0 to be accessible from VMs
        assert backend_host in [
            "0.0.0.0",
            NetworkConstants.MAIN_MACHINE_IP,
        ], f"Backend must bind to 0.0.0.0 or {NetworkConstants.MAIN_MACHINE_IP}, currently: {backend_host}"

    def test_redis_uses_standard_port(self):
        """Ensure Redis uses standard port 6379"""
        redis_config = unified_config_manager.get_redis_config()
        redis_port = redis_config.get("port")

        assert redis_port == 6379, f"Redis must use standard port 6379, currently configured for: {redis_port}"


class TestConfigurationSource:
    """Test that configuration comes from unified_config_manager"""

    def test_no_hardcoded_ips_in_redis_helper(self):
        """Redis host resolution goes through configuration, not a hardcoded module constant.

        #15051: this imported `utils.redis_helper` -- a module deleted from every
        tree years before this test ever ran (nothing collected it, so nothing
        noticed). `REDIS_HOST` was never a real export of it either. Repointed at
        the canonical accessor CLAUDE.md mandates, the same move #13286 made for
        the sibling `TIMEOUT_CONFIG` import in `test_redis_timeout_configuration`
        below. The property under test still holds and is worth guarding here:
        `autobot_shared.redis_client`'s module namespace carries no bare
        IP-shaped constant that would bypass configuration.
        """
        import re

        import autobot_shared.redis_client as canonical_redis_client

        ip_literal = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
        hardcoded = [
            name
            for name, value in vars(canonical_redis_client).items()
            if isinstance(value, str) and ip_literal.match(value)
        ]
        assert not hardcoded, (
            f"autobot_shared.redis_client carries hardcoded IP-shaped module constants: {hardcoded} "
            "-- host resolution must come from configuration, not a literal"
        )

    def test_service_discovery_has_defaults(self):
        """`service_discovery_defaults` has no SSOT equivalent (#15051); callers survive its absence.

        #13286 consolidated backend/redis/frontend host+port configuration onto
        `autobot_shared.ssot_config`, which declares no `service_discovery_defaults`
        section -- `service_discovery.py:278` and `distributed_service_discovery.py`
        both say so inline and read the section with `or {}`. This test used to
        assert four keys inside it; there is no longer any source that would ever
        populate them, so that shape was asserting a section nothing writes. What
        still has to hold is the property those two callers actually depend on:
        `get_config_section` returns `{}`, never `None`, for a section nobody
        declared, so their `or {}` is defensive rather than covering a crash.
        """
        defaults = unified_config_manager.get_config_section("service_discovery_defaults")

        assert defaults is not None, "get_config_section must return {} (not None) for an undeclared section"
        assert defaults == {}, (
            "service_discovery_defaults gained content -- service_discovery.py and "
            "distributed_service_discovery.py's `or {}` fallback should be revisited"
        )


class TestRedisConnection:
    """Test Redis connection configuration"""

    @pytest.mark.integration
    def test_redis_connectivity(self):
        """Redis serves commands on the SSOT-configured endpoint, in the SSOT-allocated DB.

        #15182: this called ``client.ping()`` and then asserted ``assert True``,
        skipping on ``ConnectionError``. There was no input under which it failed:
        with Redis it passed asserting nothing, without Redis it skipped. #15182 put
        it at 1 of the 8 tests the marker run selected from this tree; re-measured on
        this branch the selection is 19 (16 passed, 3 skipped, 17 deselected of 36
        collected), #15161 having restored the collection the earlier figure was taken
        under. Either way a whole test of this directory's signal was a constant.

        WHAT THIS TEST IS FOR, decided: not "a socket opened", but "the canonical
        accessor hands back a client wired to the parameters the SSOT declares, and
        that client serves commands". Three claims, each asserted separately so a
        failure names which one broke:

        1. ``get_redis_client()`` returns a client at all. It is documented to return
           ``None`` when Redis is disabled or the connection fails inside the manager,
           and the old body would have raised ``AttributeError`` on that path rather
           than reporting it.
        2. The pool's host and port are the ones ``unified_config_manager`` declares,
           and its ``db`` is the number ``redis-databases.yaml`` allocates to the named
           database ``main`` — the same mapping ``test_redis_db_ssot.py`` guards
           (#15181). A client that connects to something other than the configured
           endpoint is exactly the failure "connectivity" is assumed to cover.
        3. A set/get/delete round-trip. A PING handshake proves reachability; it does
           not prove the pool serves commands against the selected database.

        NO SKIP, deliberately. ``marker-tests.yml`` is the only workflow that selects
        ``integration``, and it provisions ``redis:7-alpine`` as a service container
        with a ``redis-cli ping`` health gate, so Redis is not optional where this test
        runs. An unreachable Redis there is the condition this test exists to report,
        not a reason to withhold a verdict — a skip converts the one real failure mode
        into a non-result. The ``except`` below is kept only to turn a transport error
        into a named failure instead of a bare traceback; it does not carry the value,
        which is why it does not interpolate the endpoint it dialled.
        """
        from autobot_shared.redis_management.types import DATABASE_MAPPING

        expected = unified_config_manager.get_redis_config()
        expected_db = DATABASE_MAPPING["main"]

        try:
            # Use canonical get_redis_client() pattern for consistency
            client = get_redis_client(async_client=False, database="main")
            assert client is not None, (
                "get_redis_client(database='main') returned None — Redis is disabled, "
                "or the connection failed inside the canonical accessor"
            )

            params = client.connection_pool.connection_kwargs
            assert params.get("host") == expected.get(
                "host"
            ), "Redis pool host is not the one unified_config_manager declares"
            assert params.get("port") == expected.get(
                "port"
            ), "Redis pool port is not the one unified_config_manager declares"
            assert params.get("db") == expected_db, (
                f"Redis pool selected db {params.get('db')} for database='main'; "
                f"redis-databases.yaml allocates db {expected_db}"
            )

            assert client.ping() is True, "Redis PING did not return True"

            probe_key = f"autobot:test:architecture-compliance:{uuid.uuid4().hex}"
            try:
                client.set(probe_key, "reachable")
                assert client.get(probe_key) in (
                    "reachable",
                    b"reachable",
                ), "Redis round-trip returned a different value than was written"
            finally:
                client.delete(probe_key)
        except (redis.ConnectionError, redis.TimeoutError, socket.timeout) as e:
            pytest.fail(f"Redis unreachable on the SSOT-configured endpoint: {type(e).__name__}: {e}")

    @pytest.mark.integration
    def test_redis_timeout_configuration(self):
        """Test that Redis connections have proper timeout settings.

        #13286: this read `utils.redis_helper.TIMEOUT_CONFIG`, a module that
        exists in no tree — so the check raised `ModuleNotFoundError` rather than
        asserting anything. It went unnoticed because the module it lives in
        failed to import at all, and nothing in any workflow collected this tree.

        `PoolConfig` is the canonical successor and carries the same four
        settings as typed fields, so the assertions transfer unchanged.
        """
        from autobot_shared.redis_management.config import PoolConfig

        pool = PoolConfig()

        assert pool.socket_timeout > 0, "socket_timeout must be positive"
        assert pool.socket_connect_timeout > 0, "socket_connect_timeout must be positive"
        assert pool.retry_on_timeout is True, "retry_on_timeout should be enabled"
        assert pool.max_retries > 0, "max_retries must be positive"


class TestPortConfiguration:
    """Test port assignments"""

    def test_service_ports_match_ssot_constants(self):
        """Each role's configured port matches the SSOT port config, not a hardcoded literal.

        #15194: the old test asserted fixed literals (8001, 6379, 5173, 8081, 8080,
        3000) -- inverting the "never hardcode" rule into the very assertion meant to
        guard it. It also asserted the wrong number for the browser role: 3000 is
        Grafana's port, while the SSOT default is 9001 (#4052) -- a literal-vs-literal
        comparison could not catch that, because both sides were spelled by hand from
        the same stale assumption. It also read the browser role under the wrong key
        (``browser_service``, which ``get_distributed_services_config()`` never
        populates -- the key is ``browser``), so it silently compared ``None`` to a
        literal. Comparing against ``autobot_shared.ssot_config.config.port`` directly
        holds for whatever port an operator configures, while still catching a config
        path that silently diverges from what SSOT declares.
        """
        from autobot_shared.ssot_config import config as ssot_config

        backend_config = unified_config_manager.get_backend_config()
        redis_config = unified_config_manager.get_redis_config()
        services_config = unified_config_manager.get_distributed_services_config()

        assert (
            backend_config.get("port") == ssot_config.port.backend
        ), "Backend port must come from SSOT config.port.backend"

        assert (
            redis_config.get("port") == ssot_config.port.redis
        ), "Redis port must come from SSOT config.port.redis"

        role_to_ssot_port_attr = {
            "frontend": "frontend",
            "npu_worker": "npu",
            "ai_stack": "aistack",
            "browser": "browser",
        }
        for service_key, ssot_attr in role_to_ssot_port_attr.items():
            port = services_config.get(service_key, {}).get("port")
            expected = getattr(ssot_config.port, ssot_attr)
            assert port == expected, (
                f"'{service_key}' role port ({port!r}) does not match SSOT "
                f"config.port.{ssot_attr} ({expected!r})"
            )


class TestSingleFrontendServer:
    """Test that only one frontend server is configured"""

    def test_only_one_frontend_instance(self):
        """Exactly one frontend role exists platform-wide, regardless of host count.

        #15194: the old assertion required backend and frontend to be on different
        hosts ("Backend must not run on frontend VM"), which fails a correct
        co-located or single-VM deployment where every role can legitimately share
        one host (ADR-010). ADR-005's single-frontend mandate governs how many
        frontend *processes* may run, not which host a role shares with another --
        co-location is allowed; a second frontend role is not. ``get_host_configs()``
        is the canonical fleet-wide host registry (also used to generate CORS
        origins); asserting exactly one ``frontend`` entry there is a real check on
        the schema, independent of what host that entry resolves to.
        """
        host_configs = NetworkConstants.get_host_configs()
        frontend_entries = [h for h in host_configs if h.get("id") == "frontend"]

        assert len(frontend_entries) == 1, (
            f"Expected exactly one 'frontend' role entry in get_host_configs(), "
            f"found {len(frontend_entries)}"
        )

        services_config = unified_config_manager.get_distributed_services_config()
        frontend_host = services_config.get("frontend", {}).get("host")
        assert frontend_host, "frontend role must resolve to a non-empty host"

        # Co-location is allowed: backend and frontend may legitimately share a
        # host in Docker or single-VM deployments (ADR-010). This test does not,
        # and must not, assert that they differ.


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
