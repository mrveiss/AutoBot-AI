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
    first = reporter.report()
    assert "inventory" in first
    reporter.confirm(first, delivered=True)  # only an acknowledged report counts as sent
    assert "inventory" not in reporter.report()
    state["sig"], state["git"] = (("p", 2),), "2.44"
    changed = reporter.report()
    assert changed["inventory"]["packages"] == {"git": "2.44"}
    reporter.confirm(changed, delivered=True)
    assert "inventory" not in reporter.report()
    clock.now = inventory.INVENTORY_RESEND_S + 1
    assert "inventory" in reporter.report()


def test_unchanged_signature_does_not_rescan(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    reporter.confirm(reporter.report(), delivered=True)
    state["git"] = "9.9"  # a rescan would notice; an unchanged mtime signature must not rescan
    assert reporter.report()["inventory_hash"] == reporter.report()["inventory_hash"]
    assert "inventory" not in reporter.report()


def test_a_lost_full_report_is_resent_on_the_next_heartbeat(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    lost = reporter.report()
    assert reporter.confirm(lost, delivered=False) is False
    assert "inventory" in reporter.report()  # not waiting for the 6h backstop


def test_an_acknowledged_full_report_is_not_resent(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    assert reporter.confirm(reporter.report(), delivered=True) is True
    assert "inventory" not in reporter.report()


def test_the_agent_confirms_through_the_payload_helper(monkeypatch):
    from slm.agent import heartbeat_payload

    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    monkeypatch.setattr(heartbeat_payload, "get_inventory_reporter", lambda: reporter)
    payload = {"extra_data": reporter.report()}
    assert heartbeat_payload.confirm_inventory(payload, False) is False
    assert "inventory" in reporter.report()
