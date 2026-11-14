# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The browser VM's noVNC URL is an ssot_config property (#18094)."""

import asyncio
from types import SimpleNamespace

from autobot_shared.ssot_config import AutoBotConfig
from autobot_shared.ssot_config import config as ssot_config


def _cfg(monkeypatch) -> AutoBotConfig:
    monkeypatch.setenv("AUTOBOT_BROWSER_SERVICE_HOST", "browser-host")
    monkeypatch.setenv("AUTOBOT_BACKEND_HOST", "backend-host")
    monkeypatch.setenv("AUTOBOT_VNC_PORT", "6123")
    return AutoBotConfig()


def test_browser_vnc_url_equals_the_old_compat_string(monkeypatch):
    # config.compat built f"http://{vm.browser}:{port.vnc}/vnc.html" (PLAYWRIGHT_VNC_URL
    # and get_vnc_direct_url both); pinned literally for these inputs.
    assert _cfg(monkeypatch).browser_vnc_url == "http://browser-host:6123/vnc.html"


def test_desktop_vnc_url_is_unchanged(monkeypatch):
    assert _cfg(monkeypatch).vnc_url == "http://backend-host:6123/vnc.html"


def test_research_browser_reports_the_ssot_url():
    from api.research_browser import _get_docker_browser_info

    session = SimpleNamespace(status="active")
    info = asyncio.run(_get_docker_browser_info(session))

    assert info["direct_url"] == ssot_config.browser_vnc_url
    assert info["vnc_url"] == ssot_config.browser_vnc_url.replace("vnc.html", "")
