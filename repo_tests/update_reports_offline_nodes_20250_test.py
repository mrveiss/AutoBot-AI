# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20250: the update waits for nodes, and its marker matches what the log reader looks for."""

from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, StrictUndefined

_PLAYBOOK = (
    Path(__file__).resolve().parents[1] / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml"
)
_SNAPSHOT = "[PRE-FLIGHT] Count the nodes online before the update"
_WAIT = "Wait for the nodes to report back"
_REPORT = "Report nodes still offline after the update"


def _tasks() -> list:
    plays = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    return [task for play in plays for task in play.get("tasks", []) or []]


def test_the_wait_cannot_fail_the_update_and_comes_before_the_report() -> None:
    names = [task.get("name") for task in _tasks()]
    assert names.index("Wait for the nodes to report back") < names.index("Report nodes still offline after the update")
    wait = next(t for t in _tasks() if t.get("name") == "Wait for the nodes to report back")
    assert wait["failed_when"] is False


def test_the_marker_is_the_text_the_reader_looks_for() -> None:
    report = next(t for t in _tasks() if t.get("name") == "Report nodes still offline after the update")
    assert report["debug"]["msg"].startswith("NODES OFFLINE AFTER UPDATE:")


def _task(name: str) -> dict:
    return next(t for t in _tasks() if t.get("name") == name)


def _holds(expression: str, **values: object) -> bool:
    """What Ansible would decide, rendered with jinja2 rather than matched as text."""
    rendered = Environment().from_string(f"{{% if {expression} %}}yes{{% endif %}}").render(**values)
    return rendered == "yes"


@pytest.mark.parametrize(
    "limit,counted",
    [(None, True), ("localhost,SLM", True), ("localhost,SLM,other", True), ("localhost,other", False)],
)
def test_only_a_run_touching_the_slm_host_counts_the_fleet(limit: str | None, counted: bool) -> None:
    values = {"slm_manager_inventory_host": "SLM"} | ({"ansible_limit": limit} if limit else {})
    assert _holds(_task(_SNAPSHOT)["when"], **values) is counted


def test_an_inventory_without_group_vars_skips_the_count_rather_than_stopping() -> None:
    """A temp inventory doesn't load group_vars/all.yml, so the name can be undefined."""
    env = Environment(undefined=StrictUndefined)
    rendered = env.from_string(f"{{% if {_task(_SNAPSHOT)['when']} %}}yes{{% endif %}}").render(
        ansible_limit="localhost,x"
    )
    assert rendered == ""


def test_the_snapshot_comes_before_any_restart_and_cannot_stop_the_update() -> None:
    names = [task.get("name") for task in _tasks()]
    assert names.index(_SNAPSHOT) < next(i for i, n in enumerate(names) if str(n).startswith("[PLAY 1]"))
    assert _task(_SNAPSHOT)["failed_when"] is False


@pytest.mark.parametrize(
    "before,now,done",
    [(3, 3, True), (3, 4, True), (3, 2, False), (0, 0, True)],
)
def test_the_wait_is_for_the_nodes_online_before_the_update(before: int, now: int, done: bool) -> None:
    """A node already down isn't in `before`, so it costs no wait and isn't reported."""
    values = {
        "fleet_nodes_before": {"json": {"nodes_online": before}},
        "fleet_nodes_health": {"status": 200, "json": {"nodes_online": now}},
    }
    assert _holds(_task(_WAIT)["until"], **values) is done
    report = _task(_REPORT)["when"]
    assert all(_holds(line, **values) for line in report) is (not done)


def test_no_snapshot_means_no_wait_and_no_report() -> None:
    assert _holds(_task(_WAIT)["when"], fleet_nodes_before={}) is False
    assert _holds(_task(_REPORT)["when"][0], fleet_nodes_before={}) is False
    assert _task(_WAIT)["register"] != "slm_health", "a skipped task's result would overwrite the health check"
