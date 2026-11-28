# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reconcile of the self-model from fixtures: install, removal, upgrade, node silence (#22277)."""

from datetime import datetime, timedelta, timezone

import pytest

from services.self_model_reconcile import (
    ABSENT,
    DECLARED,
    PROBED_OK,
    STALE,
    Observation,
    entity_key,
    mark_stale,
    reconcile_observations,
    rename_hosts,
    touch,
    unavailable_because,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=1)
NODE = entity_key("node", "n1")
SCOPE = {"source": "inventory", "scope_kinds": ("command", "package"), "scope_parent": NODE}


def _cmd(name: str, version: str | None = None, status: str = PROBED_OK) -> Observation:
    return Observation("command", name, status, parent_key=NODE, node_id="n1", version=version)


def _apply(rows: dict, plan) -> dict:
    return {**rows, **{u["entity_key"]: u for u in plan.upserts}}


def _run(rows: dict, observed: list, now: datetime):
    plan = reconcile_observations(rows, observed, now, **SCOPE)
    return _apply(rows, plan), plan


def test_key_is_stable_under_case_and_whitespace():
    assert entity_key("command", "  FFmpeg ", NODE) == entity_key("command", "ffmpeg", NODE)
    assert entity_key("command", "ffmpeg", NODE) != entity_key("command", "ffmpeg", entity_key("node", "n2"))
    with pytest.raises(ValueError):
        entity_key("gadget", "x")


def test_install_creates_probed_ok_with_first_and_last_seen():
    rows, plan = _run({}, [_cmd("ffmpeg", "6.0")], T0)
    row = rows[entity_key("command", "ffmpeg", NODE)]
    assert (row["status"], row["first_seen"], row["last_seen"], row["version"]) == (PROBED_OK, T0, T0, "6.0")
    assert [h["event"] for h in plan.history] == ["created"]


def test_removal_marks_absent_with_removed_at_and_keeps_history():
    rows, _ = _run({}, [_cmd("ffmpeg", "6.0"), _cmd("git")], T0)
    rows, plan = _run(rows, [_cmd("git")], T1)
    gone = rows[entity_key("command", "ffmpeg", NODE)]
    assert (gone["status"], gone["removed_at"], gone["first_seen"]) == (ABSENT, T1, T0)
    assert [(h["event"], h["new_status"]) for h in plan.history] == [("removed", ABSENT)]
    assert rows[entity_key("command", "git", NODE)]["status"] == PROBED_OK


def test_reinstall_after_removal_reappears_and_clears_removed_at():
    rows, _ = _run({}, [_cmd("ffmpeg")], T0)
    rows, _ = _run(rows, [], T1)
    rows, plan = _run(rows, [_cmd("ffmpeg")], T1 + timedelta(hours=1))
    row = rows[entity_key("command", "ffmpeg", NODE)]
    assert (row["status"], row["removed_at"]) == (PROBED_OK, None)
    assert [h["event"] for h in plan.history] == ["reappeared"]


def test_upgrade_records_a_version_change_on_the_same_entity():
    rows, _ = _run({}, [_cmd("ffmpeg", "6.0")], T0)
    rows, plan = _run(rows, [_cmd("ffmpeg", "7.1")], T1)
    assert len([k for k in rows if k.endswith("command:ffmpeg")]) == 1
    (event,) = plan.history
    assert (event["event"], event["old_version"], event["new_version"]) == ("version_changed", "6.0", "7.1")


def test_unchanged_observation_only_moves_last_seen():
    rows, _ = _run({}, [_cmd("git", "2.4")], T0)
    rows, plan = _run(rows, [_cmd("git", "2.4")], T1)
    assert plan.history == [] and not plan.changed
    assert rows[entity_key("command", "git", NODE)]["last_seen"] == T1


def test_silent_node_goes_stale_and_revives_on_the_next_report():
    rows, _ = _run({}, [_cmd("git")], T0)
    plan = mark_stale(rows.values(), T0 + timedelta(minutes=10), timedelta(minutes=5))
    rows = _apply(rows, plan)
    assert rows[entity_key("command", "git", NODE)]["status"] == STALE
    plan = touch(rows.values(), T1, "inventory")
    rows = _apply(rows, plan)
    assert rows[entity_key("command", "git", NODE)]["status"] == PROBED_OK
    assert [h["new_status"] for h in plan.history] == [PROBED_OK]


def test_a_recent_entity_is_not_stale():
    rows, _ = _run({}, [_cmd("git")], T0)
    assert mark_stale(rows.values(), T0 + timedelta(minutes=1), timedelta(minutes=5)).upserts == []


def test_declared_entity_never_probed_stays_declared():
    tool = Observation("tool", "web_fetch", DECLARED, attrs={"requires": ["curl"]})
    kwargs = {"source": "catalogue", "scope_kinds": ("tool",)}
    rows = _apply({}, reconcile_observations({}, [tool], T0, **kwargs))
    rows = _apply(rows, reconcile_observations(rows, [tool], T1, **kwargs))
    assert rows["tool:web_fetch"]["status"] == DECLARED
    assert mark_stale(rows.values(), T1 + timedelta(days=9), timedelta(minutes=5)).upserts == []


def test_a_declaration_does_not_downgrade_a_probed_entity():
    probed = Observation("service", "backend", PROBED_OK)
    declared = Observation("service", "backend", DECLARED)
    kwargs = {"source": "catalogue", "scope_kinds": ("service",)}
    rows = _apply({}, reconcile_observations({}, [probed], T0, **kwargs))
    rows = _apply(rows, reconcile_observations(rows, [declared], T1, **kwargs))
    assert rows["service:backend"]["status"] == PROBED_OK


def test_a_declaration_does_not_refresh_the_probe_freshness_it_preserves():
    probed = Observation("service", "backend", PROBED_OK)
    declared = Observation("service", "backend", DECLARED)
    kwargs = {"source": "catalogue", "scope_kinds": ("service",)}
    rows = _apply({}, reconcile_observations({}, [probed], T0, **kwargs))
    rows = _apply(rows, reconcile_observations(rows, [declared], T1, **kwargs))
    assert rows["service:backend"]["last_seen"] == T0  # only a probe is evidence of life
    rows = _apply(rows, reconcile_observations(rows, [probed], T1, **kwargs))
    assert rows["service:backend"]["last_seen"] == T1


def test_a_batch_never_marks_absent_another_sources_entity():
    rows, _ = _run({}, [_cmd("git")], T0)
    other = reconcile_observations(rows, [], T1, source="catalogue", scope_kinds=("command",))
    assert other.upserts == []


def test_requirement_on_an_absent_or_stale_command_is_unavailable_on_that_node():
    rows, _ = _run({}, [_cmd("ffmpeg"), _cmd("git")], T0)
    rows, _ = _run(rows, [_cmd("git")], T1)
    tool = {"node_id": "n1", "attrs": {"requires": ["ffmpeg", "git", "never-seen"]}}
    assert unavailable_because(tool, rows) == ["ffmpeg"]
    assert unavailable_because({"node_id": None, "attrs": {"requires": ["ffmpeg"]}}, rows) == []


def test_removing_a_required_command_makes_the_tool_unavailable_and_reinstalling_restores_it():
    """#22298: the tool follows its command through removal and reinstall on the same node."""
    tool = {"node_id": "n1", "attrs": {"requires": ["xdotool"]}}
    rows, _ = _run({}, [_cmd("xdotool", "3.0")], T0)
    assert unavailable_because(tool, rows) == []
    rows, _ = _run(rows, [], T1)
    assert unavailable_because(tool, rows) == ["xdotool"]
    rows, _ = _run(rows, [_cmd("xdotool", "3.0")], T1 + timedelta(hours=1))
    assert unavailable_because(tool, rows) == []


def test_a_host_address_becomes_the_nodes_own_id_and_an_unmanaged_host_is_kept():
    tools = [
        Observation("tool", "a", DECLARED, node_id="10.0.0.5"),
        Observation("tool", "b", DECLARED, node_id="10.0.0.9"),
        Observation("tool", "c", DECLARED),
    ]
    renamed = rename_hosts(tools, {"10.0.0.5": "node-redis"})
    assert [o.node_id for o in renamed] == ["node-redis", "10.0.0.9", None]


def test_paging_order_is_stable_when_timestamps_tie_across_a_page_boundary():
    from services.self_model_reconcile import rows_for_response

    rows = [{"id": i, "entity_key": f"tool:t{i}", "last_seen": T0} for i in (3, 1, 4, 0, 2)]
    ordered = rows_for_response(rows)
    heartbeat = rows_for_response([{**r, "last_seen": T1} if r["id"] == 4 else r for r in rows])
    assert [r["entity_key"] for r in ordered] == [f"tool:t{i}" for i in range(5)]
    assert [r["entity_key"] for r in heartbeat] == [r["entity_key"] for r in ordered]
    pages = [ordered[0:2], ordered[2:4], ordered[4:6]]
    assert [r["entity_key"] for page in pages for r in page] == [r["entity_key"] for r in ordered]


def test_a_tool_placed_by_host_address_is_unavailable_once_its_required_command_is_gone_from_that_node():
    """#22298: the backend places a tool by SSOT host; the SLM renames it to the node id its commands live under."""
    rows, _ = _run({}, [_cmd("xdotool")], T0)
    rows, _ = _run(rows, [], T1)  # the node's inventory dropped xdotool
    placed = rename_hosts(
        [Observation("tool", "bring_window_to_front", DECLARED, node_id="10.0.0.5")], {"10.0.0.5": "n1"}
    )
    tool = {"node_id": placed[0].node_id, "attrs": {"requires": ["xdotool"]}}
    assert unavailable_because(tool, rows) == ["xdotool"]
