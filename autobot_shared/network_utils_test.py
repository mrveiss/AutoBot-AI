# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
"""Pins ``is_local_ip`` behaviour that SLM's local copy lacked (#17855).

``api/nodes_execution.py`` built its own set from ``gethostbyname(hostname)``
(commonly ``127.0.1.1``), so a node's real interface address was classified
remote and routed over SSH to itself.
"""

import subprocess
from types import SimpleNamespace

import pytest

import autobot_shared.network_utils as nu


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch):
    monkeypatch.setattr(nu, "_ip_cache", None)
    monkeypatch.setattr(nu, "_ip_cache_time", 0.0)


def test_interface_address_is_local(monkeypatch):
    out = SimpleNamespace(stdout="    inet 10.9.8.7/24 brd 10.9.8.255 scope global eth0\n")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: out)
    assert nu.is_local_ip("10.9.8.7") is True
    assert nu.is_local_ip("10.9.8.8") is False


def test_loopback_names_are_local(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=""))
    for name in ("127.0.0.1", "::1", "localhost"):
        assert nu.is_local_ip(name) is True
