"""The dead-surface split must stay a split (#16816).

`--dead-surface` has existed for the life of the script and CI never asked for it,
so its output was never read and nothing exercised it. The count on its own is
large and mostly benign -- agent-facing and webhook paths have no browser caller
by design -- so a single number gets dismissed on first read and the real gap
stays invisible inside it. These tests pin the three-way split and the Company OS
subtotal, so the mode cannot regress to an undifferentiated total.
"""

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "audit_api_wiring", Path(__file__).resolve().parents[0] / "audit_api_wiring.py"
)
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


def test_agent_facing_paths_are_not_counted_as_gui_gaps():
    out = audit.classify_dead_surface(["/api/agent/work-items/next", "/agent/runs/{p}"])
    assert out["agent"] == ["/api/agent/work-items/next", "/agent/runs/{p}"]
    assert out["gui"] == []


def test_webhooks_and_health_are_machine_facing():
    out = audit.classify_dead_surface(["/api/webhooks/github", "/health", "/api/metrics"])
    assert len(out["machine"]) == 3
    assert out["gui"] == []


def test_an_ordinary_capability_with_no_caller_is_a_gui_gap():
    out = audit.classify_dead_surface(["/api/llc/companies/{p}/budget"])
    assert out["gui"] == ["/api/llc/companies/{p}/budget"]
    assert out["agent"] == [] and out["machine"] == []


def test_company_os_paths_are_recognised_for_the_subtotal():
    assert audit._is_company_os("/api/llc/companies/{p}/budget")
    assert audit._is_company_os("/api/work-items/{p}/status")
    assert not audit._is_company_os("/api/chat/sessions")


def test_the_split_partitions_the_input_exactly():
    """Every path lands in exactly one bucket — a lost path is a hidden gap."""
    paths = ["/api/agent/x", "/api/webhooks/y", "/api/llc/z", "/health", "/api/anything"]
    out = audit.classify_dead_surface(paths)
    assert sorted(out["agent"] + out["machine"] + out["gui"]) == sorted(paths)
    assert len(out["agent"]) + len(out["machine"]) + len(out["gui"]) == len(paths)
