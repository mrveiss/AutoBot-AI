# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The heartbeat inventory sends the full list only on a hash change or the backstop (#22277)."""

from slm.agent import inventory
from slm.agent.inventory import InventoryReporter, _parse_dpkg

DPKG = """Package: git
Status: install ok installed
Version: 1:2.43

Package: gone
Status: deinstall ok config-files
Version: 1.0
"""


class _Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def _reporter(monkeypatch, state: dict, clock: _Clock) -> InventoryReporter:
    monkeypatch.setattr(inventory, "signature", lambda: state["sig"])
    monkeypatch.setattr(inventory, "scan_packages", lambda: {"git": state["git"]})
    monkeypatch.setattr(inventory, "scan_commands", lambda: ["git"])
    return InventoryReporter(clock=clock)


def test_parse_dpkg_keeps_only_installed_packages():
    assert _parse_dpkg(DPKG) == {"git": "1:2.43"}


def test_full_inventory_only_when_hash_changes_or_backstop_is_due(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    assert "inventory" in reporter.report()
    assert "inventory" not in reporter.report()
    state["sig"], state["git"] = (("p", 2),), "2.44"
    changed = reporter.report()
    assert changed["inventory"]["packages"] == {"git": "2.44"}
    assert "inventory" not in reporter.report()
    clock.now = inventory.INVENTORY_RESEND_S + 1
    assert "inventory" in reporter.report()


def test_unchanged_signature_does_not_rescan(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    reporter.report()
    state["git"] = "9.9"  # a rescan would notice; an unchanged mtime signature must not rescan
    assert reporter.report()["inventory_hash"] == reporter.report()["inventory_hash"]
    assert "inventory" not in reporter.report()
