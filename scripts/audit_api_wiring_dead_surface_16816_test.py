# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
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

_SPEC = importlib.util.spec_from_file_location("dead_surface", Path(__file__).resolve().parents[0] / "dead_surface.py")
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


# -- the mode must actually EMIT the section (#16816 AC6) ---------------------
#
# The split above was tested as a pure function, and passed, while
# report_dead_surface emitted NOTHING: it logged through a module logger into a
# root logger the auditor never configures, so every line went to a WARNING-level
# void. CI asked for the measurement and received an empty answer, and nothing
# failed -- an audit mode nothing exercises is exactly how this one went unused
# for the life of the script, which is what AC6 is about.


def test_the_report_actually_emits_the_section(capsys):
    audit.report_dead_surface(["/api/llc/companies/{p}/budget"], pin=audit.UNMEASURED)
    out = capsys.readouterr().out
    assert "== BACKEND PATHS WITH NO FRONTEND CONSUMER: 1 ==" in out
    assert "NO GUI PATH TO THIS CAPABILITY:      1" in out
    assert "/api/llc/companies/{p}/budget" in out


def test_the_split_reaches_the_output_not_just_the_return_value(capsys):
    audit.report_dead_surface(
        ["/api/agent/x", "/api/webhooks/y", "/api/llc/companies/{p}/budget"], pin=audit.UNMEASURED
    )
    out = capsys.readouterr().out
    assert "agent-facing (adapters call these):  1" in out
    assert "machine-facing (webhooks, health):   1" in out
    assert "NO GUI PATH TO THIS CAPABILITY:      1" in out
    assert "of which Company OS:               1" in out


def test_an_unmeasured_pin_names_the_figure_to_pin(capsys):
    audit.report_dead_surface(["/api/llc/companies/{p}/budget"], pin=audit.UNMEASURED)
    assert "pin it to 1" in capsys.readouterr().out


def test_a_count_above_the_pin_says_so_without_failing(capsys):
    """Report-only (#16816 AC3): it says what a gate would block on, and returns."""
    audit.report_dead_surface(["/api/a", "/api/b", "/api/c"], pin="1")
    out = capsys.readouterr().out
    assert "OVER BY:  2" in out
    assert "report-only today" in out


def test_a_count_below_the_pin_asks_for_the_pin_to_be_lowered(capsys):
    audit.report_dead_surface(["/api/a"], pin="5")
    assert "lower it to 1" in capsys.readouterr().out


def test_the_job_summary_receives_the_section_when_ci_provides_one(tmp_path, monkeypatch, capsys):
    """AC1: the count and the list land in the job summary, not only the log."""
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    audit.report_dead_surface(["/api/llc/companies/{p}/budget", "/api/agent/x"], pin="7")
    capsys.readouterr()

    written = summary.read_text(encoding="utf-8")
    assert "### Backend capability the GUI cannot reach (#16816)" in written
    assert "| **no GUI path to this capability** | **1** |" in written
    assert "| of which Company OS | 1 |" in written
    assert "`/api/llc/companies/{p}/budget`" in written


def test_nothing_is_written_when_there_is_no_job_summary(monkeypatch, capsys):
    """Running locally must not need a GITHUB_STEP_SUMMARY to exist."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    audit.report_dead_surface(["/api/a"], pin="1")
    assert "== BACKEND PATHS WITH NO FRONTEND CONSUMER: 1 ==" in capsys.readouterr().out
