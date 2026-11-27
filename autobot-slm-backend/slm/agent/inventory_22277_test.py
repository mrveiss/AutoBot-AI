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


def _ack(reporter: InventoryReporter) -> bool:
    report = reporter.report()
    return reporter.confirm(report, delivered=True, acknowledged=report["inventory_hash"])


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
    reporter.confirm(first, delivered=True, acknowledged=first["inventory_hash"])  # only an acknowledged report counts as sent
    assert "inventory" not in reporter.report()
    state["sig"], state["git"] = (("p", 2),), "2.44"
    changed = reporter.report()
    assert changed["inventory"]["packages"] == {"git": "2.44"}
    reporter.confirm(changed, delivered=True, acknowledged=changed["inventory_hash"])
    assert "inventory" not in reporter.report()
    clock.now = inventory.INVENTORY_RESEND_S + 1
    assert "inventory" in reporter.report()


def test_unchanged_signature_does_not_rescan(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    _ack(reporter)
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
    assert _ack(reporter) is True
    assert "inventory" not in reporter.report()


def test_the_agent_confirms_through_the_payload_helper(monkeypatch):
    from slm.agent import heartbeat_payload

    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    monkeypatch.setattr(heartbeat_payload, "get_inventory_reporter", lambda: reporter)
    payload = {"extra_data": reporter.report()}
    assert heartbeat_payload.confirm_inventory(payload, False) is False
    assert "inventory" in reporter.report()


def test_a_heartbeat_accepted_without_the_inventory_ack_is_resent(monkeypatch):
    """The SLM took the liveness but did not store the inventory: it must not count as sent (#22280)."""
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    report = reporter.report()
    assert reporter.confirm(report, delivered=True, acknowledged=None) is True
    assert "inventory" in reporter.report()
    assert reporter.confirm(report, delivered=True, acknowledged="stale-hash") is True
    assert "inventory" in reporter.report()


def test_an_exec_permission_change_is_found_by_the_bounded_rescan(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    _ack(reporter)
    monkeypatch.setattr(inventory, "scan_commands", lambda: [])  # a mode change: the signature did not move
    assert "inventory" not in reporter.report()
    clock.now = inventory.INVENTORY_RESCAN_S + 1
    assert reporter.report()["inventory"]["commands"] == []


def test_a_failed_scan_keeps_the_snapshot_and_retries_before_caching_the_signature(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)
    good = _ack(reporter)
    state["sig"] = (("p", 2),)

    def _unreadable():
        raise PermissionError("dpkg status")

    monkeypatch.setattr(inventory, "scan_packages", _unreadable)
    assert "inventory" not in reporter.report()  # the last good snapshot stands; no empty inventory published
    monkeypatch.setattr(inventory, "scan_packages", lambda: {"git": "2.50"})
    assert reporter.report()["inventory"]["packages"] == {"git": "2.50"}  # the signature was not cached: rescanned
    assert good is True


def test_no_inventory_is_reported_before_the_first_successful_scan(monkeypatch):
    clock, state = _Clock(), {"sig": (("p", 1),), "git": "2.43"}
    reporter = _reporter(monkeypatch, state, clock)

    def _unreadable():
        raise PermissionError("dpkg status")

    monkeypatch.setattr(inventory, "scan_packages", _unreadable)
    assert reporter.report() == {}
