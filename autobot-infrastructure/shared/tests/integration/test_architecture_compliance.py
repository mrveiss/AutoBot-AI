#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Architecture Compliance Tests
=============================

Tests to ensure AutoBot's distributed architecture is properly configured
and services are running on their designated VMs.

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

    @pytest.mark.skip(
        reason=(
            "#15194: asserts a fixed VM topology the platform does not have. AutoBot "
            "runs in Docker, on one VM, or on any number the operator chooses, so this "
            "assertion is false by construction rather than merely unmet here. Skipped "
            "with the reason recorded instead of adjusted to pass: rewriting it needs "
            "the topology decision on #15194, and editing it green would hide the very "
            "defect #15051 wired this file in to expose."
        )
    )
    def test_browser_service_on_vm5(self):
        """Ensure browser service runs on VM5 (Browser VM)"""
        services_config = unified_config_manager.get_distributed_services_config()
        browser_config = services_config.get("browser_service", {})
        browser_host = browser_config.get("host")

        assert (
            browser_host == NetworkConstants.BROWSER_VM_IP
        ), f"Browser service must run on VM5 (Browser VM), currently configured for: {browser_host}"


class TestNetworkConfiguration:
    """Test network configuration compliance"""

    @pytest.mark.skip(
        reason=(
            "#15194: asserts a fixed VM topology the platform does not have. AutoBot "
            "runs in Docker, on one VM, or on any number the operator chooses, so this "
            "assertion is false by construction rather than merely unmet here. Skipped "
            "with the reason recorded instead of adjusted to pass: rewriting it needs "
            "the topology decision on #15194, and editing it green would hide the very "
            "defect #15051 wired this file in to expose."
        )
    )
    def test_no_localhost_in_distributed_services(self):
        """Ensure no services use localhost in distributed configuration"""
        services_config = unified_config_manager.get_distributed_services_config()

        for service_name, service_config in services_config.items():
            if isinstance(service_config, dict):
                host = service_config.get("host")
                if host:
                    assert host not in [
                        "localhost",
                        "127.0.0.1",
                    ], f"Service '{service_name}' uses localhost ({host}), must use actual IP"

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

    @pytest.mark.skip(
        reason=(
            "#15194: asserts a fixed VM topology the platform does not have. AutoBot "
            "runs in Docker, on one VM, or on any number the operator chooses, so this "
            "assertion is false by construction rather than merely unmet here. Skipped "
            "with the reason recorded instead of adjusted to pass: rewriting it needs "
            "the topology decision on #15194, and editing it green would hide the very "
            "defect #15051 wired this file in to expose."
        )
    )
    def test_standard_port_assignments(self):
        """Ensure services use their standard ports"""
        backend_config = unified_config_manager.get_backend_config()
        redis_config = unified_config_manager.get_redis_config()
        services_config = unified_config_manager.get_distributed_services_config()

        # Backend
        assert backend_config.get("port") == 8001, "Backend must use port 8001"

        # Redis
        assert redis_config.get("port") == 6379, "Redis must use port 6379"

        # Frontend
        frontend_port = services_config.get("frontend", {}).get("port")
        assert frontend_port == 5173, "Frontend must use port 5173"

        # NPU Worker
        npu_port = services_config.get("npu_worker", {}).get("port")
        assert npu_port == 8081, "NPU worker must use port 8081"

        # AI Stack
        ai_port = services_config.get("ai_stack", {}).get("port")
        assert ai_port == 8080, "AI stack must use port 8080"

        # Browser Service
        browser_port = services_config.get("browser_service", {}).get("port")
        assert browser_port == 3000, "Browser service must use port 3000"


class TestSingleFrontendServer:
    """Test that only one frontend server is configured"""

    @pytest.mark.skip(
        reason=(
            "#15194: asserts a fixed VM topology the platform does not have. AutoBot "
            "runs in Docker, on one VM, or on any number the operator chooses, so this "
            "assertion is false by construction rather than merely unmet here. Skipped "
            "with the reason recorded instead of adjusted to pass: rewriting it needs "
            "the topology decision on #15194, and editing it green would hide the very "
            "defect #15051 wired this file in to expose."
        )
    )
    def test_only_one_frontend_instance(self):
        """Ensure frontend only runs on VM1, not on main machine"""
        services_config = unified_config_manager.get_distributed_services_config()
        frontend_config = services_config.get("frontend", {})
        frontend_host = frontend_config.get("host")

        # Frontend must ONLY be on VM1
        assert (
            frontend_host == NetworkConstants.FRONTEND_VM_IP
        ), f"Frontend must run ONLY on VM1 ({NetworkConstants.FRONTEND_VM_IP}), found: {frontend_host}"

        # Backend should NOT be configured to run frontend
        backend_config = unified_config_manager.get_backend_config()
        backend_host = backend_config.get("host")
        assert backend_host != NetworkConstants.FRONTEND_VM_IP, "Backend must not run on frontend VM"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
