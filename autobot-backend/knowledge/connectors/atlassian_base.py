# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared core of the Atlassian Cloud connectors (Issue #18557, slice 3; parent #17312).

``confluence.py`` and ``jira.py`` were near-copies: the same Basic-auth credential
parsing, the same ``_request`` transport (differing only in the vendor name inside
three log/error strings, and in Jira sending a JSON body) and the same
``<vendor>:<connector_id>:<kind>:<key>`` source-id build/parse pair.  They live
here once, parameterised by ``vendor_name`` / the source-id ``kind``.

Outbound HTTP still goes through ``get_http_client().tracked_request`` with the
operator-instance egress policy (#13625); URL, auth and timeout are unchanged.
"""

from typing import Any, Dict, Optional

import aiohttp

from autobot_shared.http_client import get_http_client
from knowledge.connectors.base import AbstractConnector, RetryableError, instance_host_egress
from knowledge.connectors.models import ConnectorConfig

_REQUEST_TIMEOUT_SECONDS = 30.0


def build_atlassian_source_id(vendor: str, connector_id: str, kind: str, key: str) -> str:
    """Return ``<vendor>:<connector_id>:<kind>:<key>``."""
    return "%s:%s:%s:%s" % (vendor, connector_id, kind, key)


def parse_atlassian_source_id(kind: str, source_id: str) -> Optional[str]:
    """Return the trailing key of ``<vendor>:<connector_id>:<kind>:<key>``, else None."""
    parts = source_id.split(":")
    if len(parts) != 4 or parts[2] != kind:
        return None
    return parts[3]


class AtlassianConnector(AbstractConnector):
    """Basic-auth (email + API token) REST transport shared by Confluence and Jira."""

    #: Human-readable vendor used in log and error strings, e.g. ``"Jira"``.
    vendor_name: str = ""

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._email: str = cfg.get("username", "")
        self._api_token: str = cfg.get("password", "")
        self._base_url: str = cfg.get("base_url", "").rstrip("/")

    async def _get(self, path: str) -> Dict[str, Any]:
        """Make an authenticated GET request to the vendor REST API."""
        return await self._request("GET", path)

    async def _request(self, method: str, path: str, json_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make an authenticated request to the vendor REST API."""
        url = "%s%s" % (self._base_url, path)
        auth = aiohttp.BasicAuth(login=self._email, password=self._api_token)
        try:
            timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS)
            # Operator-configured instance host — private opt-in applies (#13625).
            async with get_http_client().tracked_request(
                method,
                url,
                auth=auth,
                json=json_data,
                timeout=timeout,
                suppress_error_log=True,
                guard_egress=instance_host_egress(),
            ) as resp:
                return await self._read_response(resp)
        except RetryableError:
            raise
        except aiohttp.ClientError as exc:
            self.logger.warning("%s request to %s failed: %s", self.vendor_name, url, exc)
            return {"status_code": 0, "error": str(exc)}

    async def _read_response(self, resp: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Raise RetryableError on 429/5xx, else return ``{status_code, body}``."""
        if resp.status == 429:
            raise RetryableError("%s rate-limited" % self.vendor_name, status_code=429)
        if resp.status >= 500:
            raise RetryableError("%s server error %d" % (self.vendor_name, resp.status), status_code=resp.status)
        body = await resp.json(content_type=None)
        return {"status_code": resp.status, "body": body}
