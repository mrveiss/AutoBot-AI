# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""REST URL construction and egress policy of the SLM client (#13584, #17576).

Split out of ``slm_client_test.py`` (#17576) so that file stays within its size ceiling. Every REST call
site builds its URL with ``_rest_url`` and asserts ``EGRESS_POLICY`` on it, with redirects refused, so the
test SLM origin is made internal by the module's autouse fixture.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared import egress_allowlist
from services.slm_client import SLMClient, _fetch_from_slm


@pytest.fixture(autouse=True)
def _slm_origin_is_internal(monkeypatch):
    """Make the test SLM origin internal, standing in for ``config.slm_url`` (#17576)."""
    monkeypatch.setattr(egress_allowlist, "_ssot_service_urls", lambda: ["https://slm.internal:443"])
    egress_allowlist.reset_internal_origin_state()
    yield
    egress_allowlist.reset_internal_origin_state()


class TestRestUrlPrefix:
    """REST URL construction must apply the same direct-vs-proxy decision as
    the WebSocket path (#13584).

    Before the fix, every REST call site hardcoded the direct-uvicorn form
    (``/api/...``). When ``slm_url`` pointed at the nginx proxy, the
    WebSocket correctly used ``/slm/api/ws/events`` while every REST call
    404'd — the exact ``Failed to fetch agents: HTTP 404`` signature from the
    2026-08-04 log sweep.

    A test that only exercises the default ``/api`` prefix would pass both
    before and after the fix, since the direct-uvicorn case never carried the
    bug. The proxy-form assertions below are the ones that actually pin it.
    """

    def test_direct_uvicorn_url_has_no_slm_prefix(self) -> None:
        """A direct-uvicorn slm_url (e.g. Docker Compose :8000) yields /api/... ."""
        client = SLMClient(slm_url="http://autobot-slm:8000")
        assert client._rest_url("/api/agents") == "http://autobot-slm:8000/api/agents"

    def test_proxy_url_gets_slm_prefix(self) -> None:
        """A proxy-form slm_url (nginx on 443/80) yields /slm/api/... — the
        regression case: before the fix this returned /api/agents and 404'd."""
        client = SLMClient(slm_url="https://slm.internal:443")
        assert client._rest_url("/api/agents") == "https://slm.internal:443/slm/api/agents"

    def test_proxy_url_prefix_applies_to_deployment_paths_too(self) -> None:
        """The prefix decision is per-URL, not per-endpoint — deployments get
        it too, not just /api/agents."""
        client = SLMClient(slm_url="https://slm.internal:443")
        assert client._rest_url("/api/deployments/dep-123") == "https://slm.internal:443/slm/api/deployments/dep-123"

    @pytest.mark.asyncio
    async def test_fetch_all_agents_requests_proxy_prefixed_url(self) -> None:
        """_fetch_all_agents must request the /slm-prefixed URL behind nginx,
        not the direct-uvicorn form that caused the observed 404s."""
        client = SLMClient(slm_url="https://slm.internal:443")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"agents": []})

        mock_get_ctx = MagicMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        with patch.object(client, "_get_session", AsyncMock(return_value=mock_session)):
            await client._fetch_all_agents()

        mock_session.get.assert_called_once_with("https://slm.internal:443/slm/api/agents", allow_redirects=False)

    @pytest.mark.asyncio
    async def test_list_deployments_requests_proxy_prefixed_url(self) -> None:
        """list_deployments must go through the same helper, not a literal
        /api/deployments path (#13584 call site not named in the original
        report)."""
        client = SLMClient(slm_url="https://slm.internal:443")

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(return_value={"deployments": []})

        mock_get_ctx = MagicMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        with patch.object(client, "_get_session", AsyncMock(return_value=mock_session)):
            await client.list_deployments()

        mock_session.get.assert_called_once_with(
            "https://slm.internal:443/slm/api/deployments", params={}, allow_redirects=False
        )

    @pytest.mark.asyncio
    async def test_fetch_from_slm_discovery_requests_proxy_prefixed_url(self) -> None:
        """_fetch_from_slm (module-level service discovery, #13584's 6th call
        site) must also go through _rest_url via the shared client — this is
        the one the original bug report did not name."""

        client = SLMClient(slm_url="https://slm.internal:443")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"url": "http://target:9000"})

        mock_get_ctx = MagicMock()
        mock_get_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_get_ctx)

        with (
            patch("services.slm_client.get_slm_client", return_value=client),
            patch.object(client, "_get_session", AsyncMock(return_value=mock_session)),
        ):
            result = await _fetch_from_slm("some-service")

        mock_session.get.assert_called_once_with(
            "https://slm.internal:443/slm/api/discover/some-service", allow_redirects=False
        )
        assert result == "http://target:9000"

    def test_all_rest_call_sites_use_the_shared_helper(self) -> None:
        """Pin every REST call site to `_rest_url`, so a new endpoint (or a
        regression on an existing one) cannot reintroduce a literal
        f"{self.slm_url}/api/..." construction (#13584 AC1/AC2).

        6 sites total: the 4 named in the issue (_fetch_all_agents,
        _fetch_agent_llm_config, create_deployment, get_deployment) plus
        list_deployments and _fetch_from_slm's service-discovery call, both
        found while sweeping for every occurrence rather than only the ones
        named in the report."""
        here = Path(__file__).resolve().parent
        src = "".join((here / name).read_text(encoding="utf-8") for name in ("slm_client.py", "slm_deployments.py"))

        # A floor, not a pin: a new endpoint that correctly calls _rest_url must
        # not break this test. The negative patterns below are the real guard —
        # they forbid reintroducing the hardcoded prefix whatever the count is.
        assert src.count("._rest_url(") >= 6, (
            "expected at least the 6 REST call sites routed through _rest_url "
            "(_fetch_all_agents, _fetch_agent_llm_config, create_deployment, "
            "get_deployment, list_deployments, _fetch_from_slm) — #13584"
        )
        # No call site should construct a REST URL by hand any more.
        assert (
            'f"{self.slm_url}/api/' not in src
        ), "a REST URL is bypassing _rest_url and hardcoding the direct-uvicorn prefix again"
        assert 'f"{client.slm_url}/api/' not in src, (
            "a module-level REST URL is bypassing _rest_url and hardcoding the " "direct-uvicorn prefix again"
        )
