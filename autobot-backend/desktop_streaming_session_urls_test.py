# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#22146: desktop session ports, listener host and viewer URLs come from SSOT."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import desktop_streaming_manager as dsm
from autobot_shared.ssot_config import config
from constants.network_constants import NetworkConstants


def _manager() -> dsm.VNCServerManager:
    manager = object.__new__(dsm.VNCServerManager)  # skip the host probes in __init__
    manager.novnc_available = True
    return manager


def test_port_bases_default_from_ssot() -> None:
    with (
        patch.object(dsm.VNCServerManager, "_check_vnc_availability", return_value=False),
        patch.object(dsm.VNCServerManager, "_check_novnc_availability", return_value=False),
    ):
        manager = dsm.VNCServerManager()
        explicit = dsm.VNCServerManager(port_base=7000, novnc_port_base=7100)
    assert (manager.port_base, manager.novnc_port_base) == (config.port.vnc_base, config.port.vnc)
    assert (explicit.port_base, explicit.novnc_port_base) == (7000, 7100)


def test_loopback_listener_urls_say_localhost_and_match_ssl_only(monkeypatch) -> None:
    monkeypatch.setattr(config.misc, "novnc_bind_host", "127.0.0.1")
    out = _manager()._build_session_output("s", 10, 5910, 6090)
    assert out["web_url"] == f"https://{NetworkConstants.LOCALHOST_NAME}:6090"
    assert out["vnc_url"] == f"vnc://{NetworkConstants.LOCALHOST_NAME}:5910"


def test_listener_bound_beyond_loopback_is_dialed_at_the_reachable_host(monkeypatch) -> None:
    monkeypatch.setattr(config.misc, "novnc_bind_host", "0.0.0.0")  # nosec B104
    monkeypatch.setattr(config.misc, "vnc_host", "viewer.example")
    assert _manager()._build_session_output("s", 10, 5910, 6090)["web_url"] == "https://viewer.example:6090"


def test_websockify_listener_is_not_the_api_bind(monkeypatch) -> None:
    monkeypatch.setattr(config.misc, "novnc_bind_host", "127.0.0.1")
    monkeypatch.setattr(config.vm, "main_bind", "0.0.0.0")  # nosec B104
    spawn = AsyncMock()
    with (
        patch.object(dsm.asyncio, "create_subprocess_exec", spawn),
        patch.object(dsm.VNCServerManager, "_find_websockify_command", return_value="websockify"),
    ):
        asyncio.run(_manager()._start_novnc(5910, 6090))
    args = spawn.call_args.args
    assert "--ssl-only" in args
    assert f"{config.misc.novnc_bind_host}:6090" in args and f"{NetworkConstants.LOCALHOST_NAME}:5910" in args
    assert not any(str(a).startswith("0.0.0.0") for a in args)  # nosec B104


@pytest.mark.parametrize("which", [None])
def test_websockify_is_found_through_the_ssot_search_path(which) -> None:
    with patch.object(dsm.shutil, "which", side_effect=[which, "/found/websockify"]) as lookup:
        assert _manager()._find_websockify_command() == "/found/websockify"
    assert lookup.call_args_list[1].kwargs["path"] == config.path.websockify_search_path


@pytest.mark.parametrize(
    ("bind", "expected"),
    [
        ("127.0.0.1", NetworkConstants.LOCALHOST_NAME),
        ("::1", NetworkConstants.LOCALHOST_NAME),
        ("0.0.0.0", "viewer.example"),  # nosec B104
        ("::", "viewer.example"),
        ("2001:db8::7", "[2001:db8::7]"),  # an IPv6 literal must be bracketed in a URL
        ("[::]", "viewer.example"),
        ("192.0.2.7", "192.0.2.7"),  # a specific address accepts connections only on itself
    ],
)
def test_viewer_host_follows_what_the_listener_accepts(monkeypatch, bind, expected) -> None:
    monkeypatch.setattr(config.misc, "novnc_bind_host", bind)
    monkeypatch.setattr(config.misc, "vnc_host", "viewer.example")
    assert dsm.novnc_client_host() == expected
