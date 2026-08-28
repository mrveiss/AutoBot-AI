# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fleet membership comes from the SLM node registry (#15227, #15228).

Before this, "which hosts are ours?" was answered by a literal tuple of seven
SSOT attribute names in ``api/browser_mcp.py`` and a literal array of seven
hosts in the SLM frontend's ``ssot-config.ts``. Neither could see a node the
fleet gained, and the two could drift from each other besides.

The tests that matter most here are the two failure shapes, because they look
identical from the outside and must not be:

* a registry that reports **no nodes** is an empty fleet — a fact;
* a registry that could not be **read** is not a fact about the fleet at all,
  and must never be served as one.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services import fleet_registry
from services.fleet_registry import (
    SOURCE_FALLBACK,
    SOURCE_REGISTRY,
    fleet_snapshot,
    reset_fleet_cache,
)

_FETCH = "services.fleet_registry._fetch_registry_nodes"


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_fleet_cache()
    yield
    reset_fleet_cache()


def _nodes(*specs):
    return [{"node_id": f"n{i}", "ip_address": ip, "hostname": name} for i, (ip, name) in enumerate(specs)]


# ------------------------------------------------------------ the registry answers


@pytest.mark.asyncio
async def test_membership_is_whatever_the_registry_reports():
    """No code change appears anywhere in this path — the list is the input."""
    with patch(_FETCH, AsyncMock(return_value=_nodes(("10.77.4.21", "node-eight"), ("10.77.4.22", "node-nine")))):
        snapshot = await fleet_snapshot()

    assert snapshot.source == SOURCE_REGISTRY
    assert snapshot.node_count == 2
    assert snapshot.hosts == frozenset({"10.77.4.21", "node-eight", "10.77.4.22", "node-nine"})
    assert snapshot.is_degraded is False


@pytest.mark.asyncio
async def test_a_node_removed_from_the_registry_leaves_the_snapshot():
    with patch(_FETCH, AsyncMock(return_value=_nodes(("10.77.4.21", "node-eight")))):
        before = await fleet_snapshot()
    reset_fleet_cache()
    with patch(_FETCH, AsyncMock(return_value=_nodes(("10.77.4.22", "node-nine")))):
        after = await fleet_snapshot()

    assert "10.77.4.21" in before.hosts
    assert "10.77.4.21" not in after.hosts
    assert "10.77.4.22" in after.hosts


@pytest.mark.asyncio
async def test_addresses_are_normalised():
    """A hostname's case or an IPv6 literal's brackets must not split an entry."""
    with patch(_FETCH, AsyncMock(return_value=[{"ip_address": "[FD00::1]", "hostname": "Node-Eight "}])):
        snapshot = await fleet_snapshot()

    assert snapshot.hosts == frozenset({"fd00::1", "node-eight"})


@pytest.mark.asyncio
async def test_a_malformed_node_row_is_skipped_not_fatal():
    with patch(_FETCH, AsyncMock(return_value=[{"ip_address": None}, "junk", {"hostname": "node-eight"}])):
        snapshot = await fleet_snapshot()

    assert snapshot.source == SOURCE_REGISTRY
    assert snapshot.hosts == frozenset({"node-eight"})


# ------------------------------------------- an empty fleet is not a failed read


@pytest.mark.asyncio
async def test_an_empty_registry_is_reported_as_an_empty_registry():
    """Zero nodes is a fact, and must not be dressed up as the configured set.

    This is the vacuity probe for every membership test above: if the fetch
    returning ``[]`` silently produced the seven fallback hosts, all of them
    would pass while measuring nothing.
    """
    with patch(_FETCH, AsyncMock(return_value=[])):
        snapshot = await fleet_snapshot()

    assert snapshot.source == SOURCE_REGISTRY
    assert snapshot.node_count == 0
    assert snapshot.hosts == frozenset()
    assert snapshot.is_degraded is False


@pytest.mark.asyncio
async def test_an_unreadable_registry_is_labelled_not_silently_substituted():
    """The other half: a failed read is degraded, named, and never mistaken
    for an empty fleet."""
    with patch(_FETCH, AsyncMock(side_effect=RuntimeError("SLM control link is not initialised"))):
        with patch.object(fleet_registry, "NetworkConstants", _FakeConstants()):
            snapshot = await fleet_snapshot()

    assert snapshot.source == SOURCE_FALLBACK
    assert snapshot.is_degraded is True
    assert snapshot.degraded_reason and "RuntimeError" in snapshot.degraded_reason
    assert snapshot.hosts == frozenset({"10.1.1.1", "10.1.1.2"})


@pytest.mark.asyncio
async def test_the_two_failure_shapes_are_distinguishable():
    """An empty fleet and an unreadable registry must never compare equal."""
    with patch(_FETCH, AsyncMock(return_value=[])):
        empty = await fleet_snapshot()
    reset_fleet_cache()
    with patch(_FETCH, AsyncMock(side_effect=OSError("connection refused"))):
        broken = await fleet_snapshot()

    assert empty.source != broken.source
    assert empty.is_degraded is not broken.is_degraded


@pytest.mark.asyncio
async def test_the_fallback_exempts_nothing_when_config_is_unavailable():
    """Config unavailable must report nothing, not raise and not guess."""

    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError("config unavailable")

    with patch(_FETCH, AsyncMock(side_effect=OSError("down"))):
        with patch.object(fleet_registry, "NetworkConstants", _Boom()):
            snapshot = await fleet_snapshot()

    assert snapshot.source == SOURCE_FALLBACK
    assert snapshot.hosts == frozenset()


# ------------------------------------------------------------ paging and caching


@pytest.mark.asyncio
async def test_every_page_of_the_registry_is_read():
    """A fleet larger than one page must not be silently truncated to it."""
    pages = [
        {"nodes": [{"ip_address": f"10.77.4.{i}"} for i in range(1, 101)], "total": 150},
        {"nodes": [{"ip_address": f"10.77.5.{i}"} for i in range(1, 51)], "total": 150},
    ]
    session = _FakeSession(pages)
    nodes = await _drive_fetch(session)

    assert len(nodes) == 150
    assert session.calls == [("1", "100"), ("2", "100")]


@pytest.mark.asyncio
async def test_the_snapshot_is_cached_within_its_ttl():
    """``classify_url`` runs per navigate; the fleet changes at enrolment speed."""
    fetch = AsyncMock(return_value=_nodes(("10.77.4.21", "node-eight")))
    with patch(_FETCH, fetch):
        await fleet_snapshot()
        await fleet_snapshot()

    assert fetch.await_count == 1


@pytest.mark.asyncio
async def test_force_refresh_bypasses_the_cache():
    fetch = AsyncMock(return_value=_nodes(("10.77.4.21", "node-eight")))
    with patch(_FETCH, fetch):
        await fleet_snapshot()
        await fleet_snapshot(force_refresh=True)

    assert fetch.await_count == 2


def test_the_ttl_is_env_backed_not_hardcoded():
    """A TTL nobody can change without a deploy is a hardcoded TTL."""
    import inspect

    source = inspect.getsource(fleet_registry)
    assert "AUTOBOT_FLEET_REGISTRY_TTL" in source
    assert fleet_registry.FLEET_REGISTRY_TTL_SECONDS > 0


# ------------------------------------------------------------ helpers


class _FakeConstants:
    MAIN_MACHINE_IP = "10.1.1.1"
    FRONTEND_VM_IP = "10.1.1.2"
    NPU_WORKER_VM_IP = ""
    REDIS_VM_IP = ""
    AI_STACK_VM_IP = ""
    BROWSER_VM_IP = ""
    SLM_VM_IP = ""


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, pages):
        self._pages = list(pages)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((params["page"], params["per_page"]))
        return _FakeResponse(self._pages[int(params["page"]) - 1])


class _FakeClient:
    def __init__(self, session):
        self._session = session

    async def _get_session(self):
        return self._session

    def _rest_url(self, path):
        return f"http://slm.invalid{path}"


async def _drive_fetch(session):
    """Run the real ``_fetch_registry_nodes`` against a fake SLM client."""
    with patch("services.slm_client.get_slm_client", lambda: _FakeClient(session)):
        return await fleet_registry._fetch_registry_nodes()
