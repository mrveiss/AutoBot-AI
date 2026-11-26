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
    reconcile,
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
    plan = reconcile(rows, observed, now, **SCOPE)
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
    rows = _apply({}, reconcile({}, [tool], T0, **kwargs))
    rows = _apply(rows, reconcile(rows, [tool], T1, **kwargs))
    assert rows["tool:web_fetch"]["status"] == DECLARED
    assert mark_stale(rows.values(), T1 + timedelta(days=9), timedelta(minutes=5)).upserts == []


def test_a_declaration_does_not_downgrade_a_probed_entity():
    probed = Observation("service", "backend", PROBED_OK)
    declared = Observation("service", "backend", DECLARED)
    kwargs = {"source": "catalogue", "scope_kinds": ("service",)}
    rows = _apply({}, reconcile({}, [probed], T0, **kwargs))
    rows = _apply(rows, reconcile(rows, [declared], T1, **kwargs))
    assert rows["service:backend"]["status"] == PROBED_OK


def test_a_batch_never_marks_absent_another_sources_entity():
    rows, _ = _run({}, [_cmd("git")], T0)
    other = reconcile(rows, [], T1, source="catalogue", scope_kinds=("command",))
    assert other.upserts == []


def test_requirement_on_an_absent_or_stale_command_is_unavailable_on_that_node():
    rows, _ = _run({}, [_cmd("ffmpeg"), _cmd("git")], T0)
    rows, _ = _run(rows, [_cmd("git")], T1)
    tool = {"node_id": "n1", "attrs": {"requires": ["ffmpeg", "git", "never-seen"]}}
    assert unavailable_because(tool, rows) == ["ffmpeg"]
    assert unavailable_because({"node_id": None, "attrs": {"requires": ["ffmpeg"]}}, rows) == []
