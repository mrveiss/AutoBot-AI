# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the single-node/dev-only/idle probe reclassification (#12459)
and the ``llm_awareness`` optional-dependency fix (#12458).

Each probe test asserts BOTH sides of the fix:
  - the EXPECTED-absent condition now reports a non-blocking status
    (``not_applicable`` / ``idle`` / informational ``ok``), and
  - a genuine failure still reports ``down`` (no blanket suppression).

A final scenario runs the real aggregator (``collect_system_health``) with a
representative single-node probe set to prove overall status is ``ok``, and
with one genuine failure mixed in to prove overall status is still ``down``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.system_health import (
    _PROBES,
    ComponentHealth,
    _aggregate_status,
    collect_system_health,
    register_health_probe,
)


class TestAggregateStatusExcludesExpectedStates:
    """Pure-function coverage for the not_applicable/idle rollup exclusion."""

    def test_not_applicable_and_idle_alone_roll_up_to_ok(self):
        components = [
            ComponentHealth(name="a", status="not_applicable"),
            ComponentHealth(name="b", status="idle"),
            ComponentHealth(name="c", status="ok"),
        ]
        assert _aggregate_status(components) == "ok"

    def test_down_still_wins_even_alongside_not_applicable(self):
        components = [
            ComponentHealth(name="a", status="not_applicable"),
            ComponentHealth(name="b", status="down"),
        ]
        assert _aggregate_status(components) == "down"

    def test_degraded_still_wins_even_alongside_idle(self):
        components = [
            ComponentHealth(name="a", status="idle"),
            ComponentHealth(name="b", status="degraded"),
        ]
        assert _aggregate_status(components) == "degraded"


class TestEnterpriseFeaturesProbe:
    """Issue #12459: single-node (no multi-VM topology) must not be 'down'."""

    @pytest.mark.asyncio
    async def test_missing_vm_topology_is_not_applicable(self, monkeypatch: pytest.MonkeyPatch):
        import api.enterprise_features as mod

        def _raise_topology_missing():
            raise ValueError(
                "VM topology configuration missing: All AUTOBOT_*_HOST and AUTOBOT_*_PORT environment variables must be set"
            )

        monkeypatch.setattr(mod, "get_enterprise_manager", _raise_topology_missing)

        result = await mod._probe_enterprise_features()

        assert result.status == "not_applicable"
        assert "single-node" in result.detail

    @pytest.mark.asyncio
    async def test_genuine_failure_still_down(self, monkeypatch: pytest.MonkeyPatch):
        import api.enterprise_features as mod

        def _raise_other():
            raise RuntimeError("config file corrupted")

        monkeypatch.setattr(mod, "get_enterprise_manager", _raise_other)

        result = await mod._probe_enterprise_features()

        assert result.status == "down"

    @pytest.mark.asyncio
    async def test_configured_topology_is_ok(self, monkeypatch: pytest.MonkeyPatch):
        import api.enterprise_features as mod

        monkeypatch.setattr(mod, "get_enterprise_manager", lambda: MagicMock())

        result = await mod._probe_enterprise_features()

        assert result.status == "ok"


class TestHotReloadProbe:
    """Issue #12459: dev-only watcher off is expected in every environment."""

    @pytest.mark.asyncio
    async def test_watcher_not_running_is_not_applicable(self, monkeypatch: pytest.MonkeyPatch):
        import utils.hot_reload_manager as hrm_mod
        from api.hot_reload import probe_hot_reload

        monkeypatch.setattr(hrm_mod.hot_reload_manager, "get_status", AsyncMock(return_value={"running": False}))

        result = await probe_hot_reload()

        assert result.status == "not_applicable"

    @pytest.mark.asyncio
    async def test_probe_error_still_down(self, monkeypatch: pytest.MonkeyPatch):
        import utils.hot_reload_manager as hrm_mod
        from api.hot_reload import probe_hot_reload

        monkeypatch.setattr(
            hrm_mod.hot_reload_manager, "get_status", AsyncMock(side_effect=RuntimeError("watcher crashed"))
        )

        result = await probe_hot_reload()

        assert result.status == "down"


class TestLazySingletonProbesReportIdle:
    """Issue #12459: not-yet-used lazy singletons are idle, not degraded."""

    @pytest.mark.asyncio
    async def test_chat_knowledge_not_initialized_is_idle(self, monkeypatch: pytest.MonkeyPatch):
        import api.chat_knowledge as mod

        monkeypatch.setattr(mod, "chat_knowledge_manager", None)

        result = await mod.probe_chat_knowledge(request=None)

        assert result.status == "idle"

    @pytest.mark.asyncio
    async def test_intelligent_agent_not_initialized_is_idle(self, monkeypatch: pytest.MonkeyPatch):
        import api.intelligent_agent as mod

        monkeypatch.setattr(mod, "_agent_instance", None)

        result = await mod.probe_intelligent_agent()

        assert result.status == "idle"

    @pytest.mark.asyncio
    async def test_playwright_not_initialized_is_idle(self, monkeypatch: pytest.MonkeyPatch):
        import services.playwright_service as ps_mod
        from api.playwright import probe_playwright

        monkeypatch.setattr(ps_mod, "_playwright_service", None, raising=False)

        result = await probe_playwright()

        assert result.status == "idle"


class TestRedisServiceProbeDetail:
    """Issue #12459: 'degraded' must carry an actionable reason."""

    @pytest.mark.asyncio
    async def test_degraded_detail_is_actionable_not_bare_status_word(self, monkeypatch: pytest.MonkeyPatch):
        import api.redis_service as mod

        fake_health = MagicMock(
            overall_status="degraded",
            recommendations=[
                "Service manager (SLM) could not confirm systemd status for "
                "redis-stack-server, but Redis itself responded to a direct "
                "ping — this is a service-management visibility gap, not a "
                "Redis outage"
            ],
        )
        fake_manager = MagicMock()
        fake_manager.get_health = AsyncMock(return_value=fake_health)
        monkeypatch.setattr(mod, "get_service_manager", AsyncMock(return_value=fake_manager))

        result = await mod.probe_redis_service()

        assert result.status == "degraded"
        assert result.detail != "degraded"
        assert "visibility gap" in result.detail

    @pytest.mark.asyncio
    async def test_healthy_redis_is_ok(self, monkeypatch: pytest.MonkeyPatch):
        import api.redis_service as mod

        fake_health = MagicMock(overall_status="healthy", recommendations=[])
        fake_manager = MagicMock()
        fake_manager.get_health = AsyncMock(return_value=fake_health)
        monkeypatch.setattr(mod, "get_service_manager", AsyncMock(return_value=fake_manager))

        result = await mod.probe_redis_service()

        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_critical_redis_is_still_down(self, monkeypatch: pytest.MonkeyPatch):
        import api.redis_service as mod

        fake_health = MagicMock(overall_status="critical", recommendations=["Redis process is not reachable"])
        fake_manager = MagicMock()
        fake_manager.get_health = AsyncMock(return_value=fake_health)
        monkeypatch.setattr(mod, "get_service_manager", AsyncMock(return_value=fake_manager))

        result = await mod.probe_redis_service()

        assert result.status == "down"
        assert "not reachable" in result.detail


class TestLlmAwarenessProbe:
    """Issue #12458: optional PhaseValidator absence must not force 'down'."""

    @pytest.mark.asyncio
    async def test_missing_optional_validator_is_ok_with_detail(self, monkeypatch: pytest.MonkeyPatch):
        import api.llm_awareness as mod

        fake_awareness = MagicMock()
        fake_awareness.state_tracker.validator = None
        monkeypatch.setattr(mod, "get_llm_self_awareness", lambda: fake_awareness)

        result = await mod._probe_llm_awareness()

        assert result.status == "ok"
        assert "optional component not installed" in result.detail

    @pytest.mark.asyncio
    async def test_available_validator_is_ok_no_detail(self, monkeypatch: pytest.MonkeyPatch):
        import api.llm_awareness as mod

        fake_awareness = MagicMock()
        fake_awareness.state_tracker.validator = MagicMock()
        monkeypatch.setattr(mod, "get_llm_self_awareness", lambda: fake_awareness)

        result = await mod._probe_llm_awareness()

        assert result.status == "ok"
        assert result.detail is None

    @pytest.mark.asyncio
    async def test_genuine_construction_failure_is_still_down(self, monkeypatch: pytest.MonkeyPatch):
        import api.llm_awareness as mod

        def _raise():
            raise RuntimeError("redis unreachable")

        monkeypatch.setattr(mod, "get_llm_self_awareness", _raise)

        result = await mod._probe_llm_awareness()

        assert result.status == "down"


class TestSingleNodeAggregateHealthy:
    """End-to-end: a representative single-node probe set rolls up to 'ok',
    and a genuine failure mixed into the same set still rolls up to 'down'.

    ``_PROBES`` is process-global — other already-imported modules may have
    registered real probes (e.g. a real ``redis_service`` probe that could
    itself fail in a sandboxed test environment with no reachable Redis).
    Snapshot/restore it so this test exercises ONLY the representative
    single-node set, not whatever else happens to be registered.
    """

    def setup_method(self):
        self._saved_probes = dict(_PROBES)
        _PROBES.clear()

    def teardown_method(self):
        _PROBES.clear()
        _PROBES.update(self._saved_probes)

    @pytest.mark.asyncio
    async def test_single_node_scenario_is_overall_ok(self):
        @register_health_probe("t12459_enterprise")
        async def _p1(request=None):
            return ComponentHealth(name="t12459_enterprise", status="not_applicable", detail="single-node")

        @register_health_probe("t12459_hot_reload")
        async def _p2(request=None):
            return ComponentHealth(name="t12459_hot_reload", status="not_applicable", detail="dev-only, off")

        @register_health_probe("t12459_lazy")
        async def _p3(request=None):
            return ComponentHealth(name="t12459_lazy", status="idle", detail="not yet used")

        health = await collect_system_health()

        assert health.status == "ok"
        assert {c.name for c in health.components} == {"t12459_enterprise", "t12459_hot_reload", "t12459_lazy"}

    @pytest.mark.asyncio
    async def test_genuine_failure_amongst_expected_states_is_still_down(self):
        @register_health_probe("t12459_enterprise")
        async def _p1(request=None):
            return ComponentHealth(name="t12459_enterprise", status="not_applicable", detail="single-node")

        @register_health_probe("t12459_real_failure")
        async def _p2(request=None):
            return ComponentHealth(name="t12459_real_failure", status="down", detail="database connection refused")

        health = await collect_system_health()

        assert health.status == "down"
