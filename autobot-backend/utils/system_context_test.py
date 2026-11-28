# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for utils.system_context node identity and per-host keys (#22269)."""

from types import SimpleNamespace

from services.man_page_parser import ManPageContent
from utils import system_context


def _patch(monkeypatch, ip, hostname, vms):
    monkeypatch.setattr(system_context, "get_local_ip", lambda: ip)
    monkeypatch.setattr(system_context.socket, "gethostname", lambda: hostname)
    monkeypatch.setattr(system_context, "config", SimpleNamespace(vm_definitions=vms))


def test_machine_id_comes_from_ssot_roles(monkeypatch):
    _patch(monkeypatch, "10.9.9.5", "whatever-host", {"redis": "10.9.9.5", "frontend": "10.9.9.6"})
    assert system_context.get_machine_id() == "redis"


def test_machine_id_joins_colocated_roles(monkeypatch):
    _patch(monkeypatch, "10.9.9.5", "h", {"redis": "10.9.9.5", "ai-stack": "10.9.9.5"})
    assert system_context.get_machine_id() == "ai-stack+redis"


def test_unknown_host_uses_its_own_hostname_not_a_hardcoded_map(monkeypatch):
    """A hostname the old map knew ('kali', 'autobot-redis') is no longer rewritten."""
    _patch(monkeypatch, "10.1.2.3", "Kali.example", {"redis": "10.9.9.5"})
    assert system_context.get_machine_id() == "kali"


def test_man_page_metadata_carries_per_host_unique_key():
    page = ManPageContent(command="ls", section="1")
    ctx = {"machine_id": "Redis", "os_name": "Kali"}
    assert page.get_metadata_for_storage(ctx)["unique_key"] == "redis:kali:ls:1"
    assert "unique_key" not in page.get_metadata_for_storage({"machine_id": "x"})
