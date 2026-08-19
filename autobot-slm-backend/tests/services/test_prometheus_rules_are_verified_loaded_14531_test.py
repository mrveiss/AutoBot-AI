# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The monitoring role verifies rules REACHED the server (#14531).

The deployed host ran for four months with `rule_files: []` and 0 loaded rules.
Every task in the role reported changed/ok throughout: the rule files were found
in the repo, an assert confirmed they were found, they were copied to disk, and
the config template pointed at them. None of that is evidence that the running
Prometheus read any of it, and nothing asked.

So no alert could fire — not the cgroup memory alerts (#13765), not the
chat-SSOT rules (#7590), not the TTS ones (#13767). An alerting stack with zero
rules and a fleet in perfect health produce exactly the same observable output:
silence.

These tests assert the role asks the server what it loaded, and that the check
counts rules rather than groups — a group that parsed but held nothing would
satisfy a groups-only check while alerting on nothing.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_TASKS = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "monitoring" / "tasks" / "prometheus.yml"


def _tasks() -> list[dict]:
    return yaml.safe_load(_TASKS.read_text(encoding="utf-8"))


def _module(task: dict, name: str) -> dict:
    for key in (name, f"ansible.builtin.{name}"):
        if isinstance(task.get(key), dict):
            return task[key]
    return {}


def _rules_query() -> tuple[int, dict]:
    """Index and arguments of the task that queries the running server."""
    for index, task in enumerate(_tasks()):
        uri = _module(task, "uri")
        if uri and "/api/v1/rules" in str(uri.get("url", "")):
            return index, uri
    raise AssertionError("no task asks the running Prometheus which rules it loaded")


def test_the_role_asks_the_server_what_it_loaded():
    """The regression: the role proved the files existed and stopped there."""
    _, uri = _rules_query()
    assert uri.get("url", "").endswith("/api/v1/rules")


def test_the_query_runs_after_the_restart_is_applied():
    """Asking before the restart reports the OLD server's rules.

    The config change notifies a handler, and handlers run at the end of the
    play unless flushed — so without the flush this would read the state the
    change was meant to fix and pass.
    """
    tasks = _tasks()
    query_index, _ = _rules_query()
    flushes = [
        i for i, t in enumerate(tasks) if str(t.get("ansible.builtin.meta") or t.get("meta") or "") == "flush_handlers"
    ]
    assert flushes, "handlers are never flushed, so the query reads the pre-restart server"
    assert min(flushes) < query_index, "the restart is flushed after the verification that depends on it"


def test_the_assertion_counts_rules_not_groups():
    """A group that parsed but contains nothing alerts on nothing.

    Counting groups would accept that, which is the same shape as counting the
    files on disk and calling it loaded.
    """
    tasks = _tasks()
    query_index, _ = _rules_query()
    asserts = [_module(t, "assert") for t in tasks[query_index:] if _module(t, "assert")]
    assert asserts, "nothing asserts on the query result"
    conditions = " ".join(str(c) for a in asserts for c in a.get("that", []))
    assert "rules" in conditions, "the assertion does not look at the rules within each group"
    assert "sum" in conditions, "the assertion does not total the rules, so an empty group would pass"


def test_the_verification_is_gated_by_the_same_flag_as_the_source_check():
    """A node that legitimately ships no rules already has a way to say so.

    Introducing a second, differently-named escape hatch is how two checks come
    to disagree about whether this host is supposed to have alerts.
    """
    tasks = _tasks()
    query_index, _ = _rules_query()
    guarded = [
        t
        for t in tasks[query_index:]
        if _module(t, "assert") and "prometheus_alert_rules_required" in str(t.get("when", ""))
    ]
    assert guarded, "the loaded-rules assertion is not gated by prometheus_alert_rules_required"


def test_the_query_retries_rather_than_racing_the_restart():
    """Prometheus takes a moment to serve after a restart; a single attempt
    would fail for timing rather than for the condition under test."""
    _, uri = _rules_query()
    task = next(t for t in _tasks() if _module(t, "uri") is uri or _module(t, "uri") == uri)
    assert int(task.get("retries", 0)) > 1, "the query does not retry"
    assert task.get("until"), "the query has retries but no success condition"
