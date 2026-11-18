# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deployment API methods of :class:`services.slm_client.SLMClient` (Issue #3407).

Split out of ``slm_client.py`` (#17576) so that module stays within its file-size ceiling. The mixin uses
the client's own ``_get_session`` and ``_rest_url`` (so the direct-uvicorn vs nginx-prefix decision stays in
one place) and asserts ``EGRESS_POLICY`` on each URL before requesting it, with redirects refused.
"""

from __future__ import annotations

from autobot_shared.http_egress_guard import assert_egress_policy
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class SLMDeploymentsMixin:
    """``create_deployment`` / ``get_deployment`` / ``list_deployments`` for the SLM client."""

    async def create_deployment(self, payload: dict) -> dict:
        """
        Create a new deployment via POST /api/deployments.

        Args:
            payload: Dict with node_id, roles, and optional extra_data.

        Returns:
            Raw SLM response dict with deployment_id, node_id, status, etc.

        Raises:
            aiohttp.ClientResponseError: On non-2xx HTTP responses.
        """
        session = await self._get_session()
        url = self._rest_url("/api/deployments")
        await assert_egress_policy(url)
        async with session.post(url, json=payload, allow_redirects=False) as response:
            response.raise_for_status()
            data = await response.json()
        logger.info(
            "SLM deployment created: %s on node %s",
            data.get("deployment_id"),
            data.get("node_id"),
        )
        return data

    async def get_deployment(self, deployment_id: str) -> dict:
        """
        Fetch a deployment by ID via GET /api/deployments/{deployment_id}.

        Args:
            deployment_id: SLM deployment identifier.

        Returns:
            Raw SLM response dict.

        Raises:
            aiohttp.ClientResponseError: On non-2xx HTTP responses.
        """
        session = await self._get_session()
        url = self._rest_url(f"/api/deployments/{deployment_id}")
        await assert_egress_policy(url)
        async with session.get(url, allow_redirects=False) as response:
            response.raise_for_status()
            return await response.json()

    async def list_deployments(self, node_id: str | None = None) -> dict:
        """
        List deployments via GET /api/deployments, optionally filtered by node.

        Args:
            node_id: Optional node identifier filter.

        Returns:
            Raw SLM response dict with a ``deployments`` key.

        Raises:
            aiohttp.ClientResponseError: On non-2xx HTTP responses.
        """
        session = await self._get_session()
        params = {}
        if node_id is not None:
            params["node_id"] = node_id
        url = self._rest_url("/api/deployments")
        await assert_egress_policy(url)
        async with session.get(url, params=params, allow_redirects=False) as response:
            response.raise_for_status()
            return await response.json()
