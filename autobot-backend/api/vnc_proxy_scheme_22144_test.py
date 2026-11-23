# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22144: websockify is --ssl-only, so scheme and timeouts are derived, not literal."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api import infrastructure as infra
from api import vnc_proxy


def test_upstream_endpoints_use_the_ssl_only_scheme():
    assert all(url.startswith("https://") for url in vnc_proxy.VNC_ENDPOINTS.values())


@pytest.mark.parametrize(
    ("endpoint", "ws"),
    [("https://h:6080", "wss://h:6080/websockify"), ("http://h:6080", "ws://h:6080/websockify")],
)
def test_websocket_scheme_follows_the_endpoint_scheme(endpoint, ws):
    assert vnc_proxy._websockify_url(endpoint) == ws


def test_timeouts_are_env_backed_constants():
    assert vnc_proxy.VNC_STATUS_PROBE_TIMEOUT_S > 0 and vnc_proxy.VNC_OBSERVATION_TIMEOUT_S > 0


@pytest.mark.asyncio
async def test_control_lock_refuses_a_non_secrets_host_id(monkeypatch):
    from api.schemas_system import DesktopControlAcquireRequest

    monkeypatch.setattr(infra, "_load_secrets_hosts", lambda: [])
    with patch("api.vnc_proxy.acquire_human_control") as acquire:
        with pytest.raises(HTTPException) as exc:
            await vnc_proxy.acquire_desktop_control(
                "desktop", DesktopControlAcquireRequest(session_id="fleet-node-7"), current_user={"username": "a"}
            )
    assert exc.value.status_code == 404
    acquire.assert_not_called()
