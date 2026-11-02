# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20250: the update waits for nodes, and its marker matches what the log reader looks for."""

from pathlib import Path

import yaml

_PLAYBOOK = (
    Path(__file__).resolve().parents[1] / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml"
)


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


def test_a_per_node_update_doesnt_wait_for_the_fleet() -> None:
    wait = next(t for t in _tasks() if t.get("name") == "Wait for the nodes to report back")
    assert "groups['slm_server']" in wait["when"], "self-update and per-node runs both limit to localhost,<x>"
    assert wait["register"] != "slm_health", "a skipped task's result would overwrite the health check"


def test_the_count_leaves_out_nodes_not_meant_to_be_online() -> None:
    wait = next(t for t in _tasks() if t.get("name") == "Wait for the nodes to report back")
    assert "nodes_expected_online" in wait["until"]
