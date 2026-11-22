# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Role-owner and node-service API methods of :class:`services.slm_client.SLMClient` (#16346).

The backend's Redis service manager used to build its own requests to the SLM: no credential, and a node id taken
from an environment variable that bare-metal installs never set. These methods are the credentialed, egress-guarded
way to ask the SLM which node holds a role and to read or act on that node's services. Like
:mod:`services.slm_deployments` the mixin uses the client's own ``_get_session`` (bearer re-resolved per call) and
``_rest_url`` (the direct-uvicorn vs nginx-prefix decision stays in one place), asserts ``EGRESS_POLICY`` on each URL
and refuses redirects. A non-2xx answer raises ``aiohttp.ClientResponseError`` so a caller can tell a refused
credential (401/403) from a missing node (404) instead of reading both as an empty result.
"""

from __future__ import annotations

from urllib.parse import quote

from autobot_shared.http_egress_guard import assert_egress_policy


class SLMNodeServicesMixin:
    """``get_role_owners`` / ``list_node_services`` / ``node_service_action`` for the SLM client."""

    async def _slm_json(self, method: str, path: str, **kwargs) -> dict:
        session = await self._get_session()
        url = self._rest_url(path)
        await assert_egress_policy(url)
        async with session.request(method, url, allow_redirects=False, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    async def get_role_owners(self) -> dict[str, list[str]]:
        """``role name -> node ids`` that hold it, via GET /api/roles/owners."""
        data = await self._slm_json("GET", "/api/roles/owners")
        return data.get("owners", {})

    async def list_node_services(self, node_id: str, search: str | None = None, per_page: int = 50) -> dict:
        """The services the SLM tracks on a node, via GET /api/nodes/{node_id}/services."""
        params = {"per_page": str(per_page)}
        if search:
            params["search"] = search
        return await self._slm_json("GET", f"/api/nodes/{quote(node_id, safe='')}/services", params=params)

    async def node_service_action(self, node_id: str, service_name: str, action: str) -> dict:
        """Start, stop or restart a node's service, via POST /api/nodes/{node_id}/services/{name}/{action}."""
        path = f"/api/nodes/{quote(node_id, safe='')}/services/{quote(service_name, safe='')}/{quote(action, safe='')}"
        return await self._slm_json("POST", path)
