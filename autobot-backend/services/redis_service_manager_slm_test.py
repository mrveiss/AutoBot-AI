# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RedisServiceManager's SLM calls: node resolution, credential and failure reporting (Issues #933, #16346)."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

import services.redis_service_errors as redis_service_errors
import services.redis_service_manager as redis_service_manager_module
from services.redis_service_errors import clear_resolved_node, resolve_redis_node_id
from services.redis_service_manager import (
    RedisConnectionError,
    RedisNodeUnresolvedError,
    RedisServiceManager,
    RedisSlmAccessError,
)


@pytest.fixture(autouse=True)
def _fresh_node_cache():
    clear_resolved_node()
    yield
    clear_resolved_node()


@pytest.fixture()
def manager():
    """A RedisServiceManager with a configured node id."""
    return RedisServiceManager(slm_node_id="04-Databases", service_name="redis-stack-server")


def _client(owners=None, services=None, action=None, error=None):
    """A fake SLMClient; *error* is raised by every call."""
    client = MagicMock()
    for name, value in (
        ("get_role_owners", owners if owners is not None else {}),
        ("list_node_services", services if services is not None else {"services": []}),
        ("node_service_action", action if action is not None else {"success": True, "message": ""}),
    ):
        setattr(client, name, AsyncMock(side_effect=error) if error else AsyncMock(return_value=value))
    return client


def _http_error(status: int) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=status)


def _patched(client):
    return patch("services.redis_service_manager.get_slm_client", return_value=client)


class TestInit:
    """Tests for RedisServiceManager initialisation."""

    def test_no_longer_raises_not_implemented(self) -> None:
        assert RedisServiceManager() is not None

    def test_defaults_from_env(self, monkeypatch) -> None:
        # _DEFAULT_REDIS_NODE_ID is resolved once at import time from ssot_config, so patch the module constant.
        monkeypatch.setattr(redis_service_manager_module, "_DEFAULT_REDIS_NODE_ID", "04-DBs")
        assert RedisServiceManager().slm_node_id == "04-DBs"

    def test_explicit_param_overrides_env(self) -> None:
        assert RedisServiceManager(slm_node_id="custom-node").slm_node_id == "custom-node"


class TestNodeResolution:
    """The Redis node is the configured id, else the SLM's ``redis`` role owner (#16346)."""

    @pytest.mark.asyncio
    async def test_a_configured_id_is_used_without_asking_the_slm(self, manager) -> None:
        client = _client()
        assert await resolve_redis_node_id(client, manager.slm_node_id) == "04-Databases"
        client.get_role_owners.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_unset_id_resolves_to_the_role_owner(self) -> None:
        client = _client(owners={"redis": ["07-Redis"], "backend": ["01-Main"]})
        assert await resolve_redis_node_id(client, "") == "07-Redis"

    @pytest.mark.asyncio
    async def test_a_resolved_owner_is_reused_until_its_ttl_ends(self, monkeypatch) -> None:
        clock = [1000.0]
        monkeypatch.setattr("services.redis_service_errors.time.monotonic", lambda: clock[0])
        client = _client(owners={"redis": ["07-Redis"]})
        assert await resolve_redis_node_id(client, "") == "07-Redis"
        assert await resolve_redis_node_id(client, "") == "07-Redis"
        assert client.get_role_owners.await_count == 1
        clock[0] += redis_service_errors.REDIS_NODE_CACHE_TTL_S + 1
        await resolve_redis_node_id(client, "")
        assert client.get_role_owners.await_count == 2

    @pytest.mark.asyncio
    async def test_a_failed_lookup_is_never_cached(self) -> None:
        with pytest.raises(RedisNodeUnresolvedError):
            await resolve_redis_node_id(_client(owners={}), "")
        client = _client(owners={"redis": ["n9"]})
        assert await resolve_redis_node_id(client, "") == "n9"

    @pytest.mark.asyncio
    async def test_no_owner_fails_loudly_instead_of_querying_an_empty_id(self) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        client = _client(owners={"backend": ["01-Main"]})
        with pytest.raises(RedisNodeUnresolvedError):
            await resolve_redis_node_id(client, mgr.slm_node_id)
        with _patched(client), pytest.raises(RedisNodeUnresolvedError):
            await mgr._slm_get_service_status()
        client.list_node_services.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 403])
    async def test_a_refused_credential_on_the_role_lookup_is_an_access_error(self, status) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        with pytest.raises(RedisSlmAccessError):
            await resolve_redis_node_id(_client(error=_http_error(status)), mgr.slm_node_id)


class TestSlmServiceAction:
    """Tests for _slm_service_action."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", ["start", "stop", "restart"])
    async def test_action_goes_to_the_resolved_node_and_service(self, manager, action) -> None:
        client = _client(action={"success": True, "message": action})
        with _patched(client):
            ok, msg = await manager._slm_service_action(action)
        assert (ok, msg) == (True, action)
        client.node_service_action.assert_awaited_once_with("04-Databases", "redis-stack-server", action)

    @pytest.mark.asyncio
    async def test_raises_when_the_slm_client_is_not_initialised(self, manager) -> None:
        with _patched(None), pytest.raises(RedisConnectionError, match="not initialised"):
            await manager._slm_service_action("start")

    @pytest.mark.asyncio
    async def test_raises_on_transport_error(self, manager) -> None:
        with _patched(_client(error=Exception("connection refused"))), pytest.raises(RedisConnectionError):
            await manager._slm_service_action("start")

    @pytest.mark.asyncio
    async def test_a_refused_credential_is_an_access_error(self, manager) -> None:
        with _patched(_client(error=_http_error(401))), pytest.raises(RedisSlmAccessError):
            await manager._slm_service_action("start")

    @pytest.mark.asyncio
    async def test_another_http_error_is_a_connection_error(self, manager) -> None:
        with _patched(_client(error=_http_error(500))), pytest.raises(RedisConnectionError, match="500"):
            await manager._slm_service_action("start")


class TestSlmGetServiceStatus:
    """Tests for _slm_get_service_status and get_service_status."""

    @pytest.mark.asyncio
    async def test_returns_running_when_service_found(self, manager) -> None:
        client = _client(services={"services": [{"service_name": "redis-stack-server", "status": "running"}]})
        with _patched(client):
            assert await manager._slm_get_service_status() == "running"
        client.list_node_services.assert_awaited_once_with("04-Databases", search="redis-stack-server")

    @pytest.mark.asyncio
    async def test_a_lookalike_unit_listed_first_is_not_the_service(self, manager) -> None:
        rows = [
            {"service_name": "backup-redis-stack-server", "status": "failed"},
            {"service_name": "redis-stack-server", "status": "running"},
        ]
        with _patched(_client(services={"services": rows})):
            assert await manager._slm_get_service_status() == "running"

    @pytest.mark.asyncio
    async def test_only_a_lookalike_unit_means_unknown(self, manager) -> None:
        rows = [{"service_name": "backup-redis-stack-server", "status": "running"}]
        with _patched(_client(services={"services": rows})):
            assert await manager._slm_get_service_status() == "unknown"

    @pytest.mark.asyncio
    async def test_returns_unknown_only_when_the_slm_does_not_track_the_service(self, manager) -> None:
        with _patched(_client(services={"services": []})):
            assert await manager._slm_get_service_status() == "unknown"

    @pytest.mark.asyncio
    async def test_a_refused_credential_is_an_access_error_not_unknown(self, manager) -> None:
        with _patched(_client(error=_http_error(401))), pytest.raises(RedisSlmAccessError):
            await manager._slm_get_service_status()

    @pytest.mark.asyncio
    async def test_get_service_status_surfaces_an_unresolved_node_and_a_refused_credential(self) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        with _patched(_client(owners={})), pytest.raises(RedisNodeUnresolvedError):
            await mgr.get_service_status(use_cache=False)
        with _patched(_client(error=_http_error(403))), pytest.raises(RedisSlmAccessError):
            await RedisServiceManager(slm_node_id="n").get_service_status(use_cache=False)

    @pytest.mark.asyncio
    async def test_a_transport_failure_still_reads_as_unknown(self, manager) -> None:
        with _patched(_client(error=Exception("timeout"))):
            status = await manager.get_service_status(use_cache=False)
        assert status.status == "unknown"


class TestCheckRedisConnectivity:
    """Tests for _check_redis_connectivity (Issue #933)."""

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_ping(self, manager) -> None:
        # _check_redis_connectivity imports get_async_redis_client locally from
        # autobot_shared.redis_client (not a services.redis_service_manager
        # module attribute), so the patch target must be the source module.
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            AsyncMock(return_value=mock_client),
        ):
            connected, response_ms = await manager._check_redis_connectivity()
        assert connected is True
        assert response_ms >= 0

    @pytest.mark.asyncio
    async def test_returns_false_on_ping_failure(self, manager) -> None:
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=Exception("connection refused"))
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            AsyncMock(return_value=mock_client),
        ):
            connected, response_ms = await manager._check_redis_connectivity()
        assert connected is False
        assert response_ms == 0.0


class TestRefusalsAreNotFoldedIntoResults:
    """An unresolved node or a refused credential reaches the caller from start/stop/restart too (#22030)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation", ["start_service", "stop_service", "restart_service"])
    async def test_a_refused_credential_is_raised(self, manager, operation) -> None:
        with _patched(_client(error=_http_error(401))), pytest.raises(RedisSlmAccessError):
            await getattr(manager, operation)()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("operation", ["start_service", "stop_service", "restart_service"])
    async def test_an_unresolved_node_is_raised(self, operation) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        with _patched(_client(owners={})), pytest.raises(RedisNodeUnresolvedError):
            await getattr(mgr, operation)()

    @pytest.mark.asyncio
    async def test_the_refusal_is_counted_as_an_error(self, manager) -> None:
        with _patched(_client(error=_http_error(403))), pytest.raises(RedisSlmAccessError):
            await manager.start_service()
        assert await manager._get_error_count_last_hour() >= 1

    @pytest.mark.asyncio
    async def test_a_transport_failure_is_still_a_failed_result(self, manager) -> None:
        with _patched(_client(error=Exception("down"))):
            result = await manager.start_service()
        assert result.success is False


class TestAMovedRoleIsNotHitUntilTheCacheExpires:
    """A failure clears the cached node id, so the next call asks the SLM where the role is now (#22030)."""

    @staticmethod
    def _moving(owner_after: str):
        client = _client(owners={"redis": ["old"]})
        client.get_role_owners = AsyncMock(side_effect=[{"redis": ["old"]}, {"redis": [owner_after]}])
        return client

    @pytest.mark.asyncio
    async def test_a_failed_action_clears_the_cached_node(self) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        client = self._moving("new")
        client.node_service_action = AsyncMock(side_effect=_http_error(404))
        with _patched(client):
            with pytest.raises(RedisConnectionError):
                await mgr._slm_service_action("start")
            client.node_service_action = AsyncMock(return_value={"success": True})
            await mgr._slm_service_action("start")
        client.node_service_action.assert_awaited_once_with("new", "redis-stack-server", "start")

    @pytest.mark.asyncio
    async def test_a_failed_status_query_clears_the_cached_node(self) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        client = self._moving("new")
        client.list_node_services = AsyncMock(side_effect=_http_error(404))
        with _patched(client):
            with pytest.raises(RedisConnectionError):
                await mgr._slm_get_service_status()
            client.list_node_services = AsyncMock(return_value={"services": []})
            await mgr._slm_get_service_status()
        assert client.list_node_services.await_args.args[0] == "new"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [TimeoutError(), ConnectionError("reset"), aiohttp.ClientConnectionError()])
    async def test_a_timeout_or_connection_error_on_status_clears_the_cached_node(self, error) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        client = self._moving("new")
        client.list_node_services = AsyncMock(side_effect=error)
        with _patched(client):
            with pytest.raises(type(error)):
                await mgr._slm_get_service_status()
            client.list_node_services = AsyncMock(return_value={"services": []})
            await mgr._slm_get_service_status()
        assert client.list_node_services.await_args.args[0] == "new"

    @pytest.mark.asyncio
    async def test_a_refusal_clears_the_cached_node(self) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        client = self._moving("new")
        client.list_node_services = AsyncMock(side_effect=_http_error(401))
        with _patched(client):
            with pytest.raises(RedisSlmAccessError):
                await mgr.start_service()
            assert await resolve_redis_node_id(client, "") == "new"

    @pytest.mark.asyncio
    async def test_a_success_keeps_the_cached_node(self) -> None:
        mgr = RedisServiceManager(slm_node_id="")
        client = _client(
            owners={"redis": ["old"]},
            services={"services": [{"service_name": "redis-stack-server", "status": "running"}]},
        )
        with _patched(client):
            await mgr._slm_get_service_status()
            await mgr._slm_get_service_status()
        assert client.get_role_owners.await_count == 1


class TestAClearDuringTheLookupIsNotUndone:
    """A clear that lands while the role lookup is in flight must not be overwritten by its stale answer (#22030)."""

    @pytest.mark.asyncio
    async def test_the_overlapping_lookup_does_not_re_cache(self) -> None:
        client = _client()
        answers = iter([{"redis": ["stale"]}, {"redis": ["fresh"]}])

        async def _owners():
            if "stale" not in seen:
                seen.append("stale")
                clear_resolved_node()  # the role moved while this request was in flight
            return next(answers)

        seen: list[str] = []
        client.get_role_owners = AsyncMock(side_effect=_owners)
        assert await resolve_redis_node_id(client, "") == "stale"  # the caller still gets its answer
        assert await resolve_redis_node_id(client, "") == "fresh"  # but it was not cached

    @pytest.mark.asyncio
    async def test_a_lookup_without_an_overlapping_clear_is_cached(self) -> None:
        client = _client(owners={"redis": ["n1"]})
        await resolve_redis_node_id(client, "")
        await resolve_redis_node_id(client, "")
        assert client.get_role_owners.await_count == 1


class TestARefusalOnTheActionAfterAPermittingStatus:
    """The status allowed the action, then the SLM refused it: the refusal is raised, not folded (#22030)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "operation,status,action", [("start_service", "stopped", "start"), ("stop_service", "running", "stop")]
    )
    @pytest.mark.parametrize("error_status", [401, 403])
    async def test_a_refusal_on_the_action_is_raised(self, manager, operation, status, action, error_status) -> None:
        client = _client(services={"services": [{"service_name": "redis-stack-server", "status": status}]})
        client.node_service_action = AsyncMock(side_effect=_http_error(error_status))
        with _patched(client), pytest.raises(RedisSlmAccessError):
            await getattr(manager, operation)()
        client.node_service_action.assert_awaited_once_with("04-Databases", "redis-stack-server", action)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "operation,status,action", [("start_service", "stopped", "start"), ("stop_service", "running", "stop")]
    )
    async def test_a_transport_failure_on_the_action_fails_the_operation(
        self, manager, operation, status, action
    ) -> None:
        """The node resolves before the action, so the action cannot be "unresolved"; a dropped call fails it."""
        client = _client(services={"services": [{"service_name": "redis-stack-server", "status": status}]})
        client.node_service_action = AsyncMock(side_effect=aiohttp.ClientConnectionError("down"))
        with _patched(client):
            result = await getattr(manager, operation)()
        assert result.success is False
        assert redis_service_errors._resolved is None, "a failed action must drop the cached node"
        client.node_service_action.assert_awaited_once_with("04-Databases", "redis-stack-server", action)


class TestHealthSurvivesARefusedStatusLookup:
    """A refused status lookup leaves the status unknown; the PING still decides health (#22030)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [_http_error(401), _http_error(403)])
    async def test_a_working_ping_is_degraded_not_critical(self, manager, error) -> None:
        pinged = AsyncMock(return_value=(True, 5.0))
        with _patched(_client(error=error)), patch.object(manager, "_check_redis_connectivity", pinged):
            report = await manager.get_health()
        pinged.assert_awaited_once()
        assert (report.overall_status, report.connectivity) == ("degraded", True)

    @pytest.mark.asyncio
    async def test_a_failing_ping_is_critical(self, manager) -> None:
        pinged = AsyncMock(return_value=(False, 0.0))
        with _patched(_client(error=_http_error(401))), patch.object(manager, "_check_redis_connectivity", pinged):
            report = await manager.get_health()
        assert report.overall_status == "critical"
