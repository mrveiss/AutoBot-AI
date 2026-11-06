# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A rollback's deploy ref is carried to the playbook only while the rollback is in flight (#20214)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from services import rollback_target as rt

SHA = "a" * 40


async def test_nothing_is_added_outside_a_rollback(monkeypatch):
    async def _no_plan():
        return None

    monkeypatch.setattr(rt, "_read_plan_ref", _no_plan)
    assert await rt.deploy_ref_vars(rt.ROLLBACK_PLAYBOOK) == {}


async def test_inside_the_scope_the_playbook_gets_the_ref_and_the_rollback_flag():
    with rt.rollback_scope(SHA):
        assert await rt.deploy_ref_vars(rt.ROLLBACK_PLAYBOOK) == {"deploy_ref": SHA, "deploy_is_rollback": "true"}
    assert rt.current_rollback_ref() is None


async def test_other_playbooks_are_never_touched():
    with rt.rollback_scope(SHA):
        assert await rt.deploy_ref_vars("provision-fleet-roles.yml") == {}


async def test_a_task_started_in_the_scope_keeps_it_like_the_fire_and_forget_self_update():
    async def _child() -> str | None:
        return rt.current_rollback_ref()

    with rt.rollback_scope(SHA):
        task = asyncio.create_task(_child())
    assert await task == SHA


async def test_after_the_scope_ends_the_next_run_deploys_main_again(monkeypatch):
    async def _no_plan():
        return None

    monkeypatch.setattr(rt, "_read_plan_ref", _no_plan)
    with rt.rollback_scope(SHA):
        pass
    assert await rt.deploy_ref_vars(rt.ROLLBACK_PLAYBOOK) == {}


@pytest.mark.parametrize("bad", ["main", "--output=x", "A" * 40, "a" * 39, "", None, "a" * 40 + "\n"])
def test_only_a_full_lowercase_commit_id_can_be_a_target(bad):
    assert rt.is_full_sha(bad) is False
    with pytest.raises(ValueError):
        with rt.rollback_scope(bad):
            pass


async def test_a_restarted_process_reads_the_ref_from_the_plan(monkeypatch):
    async def _plan():
        return SHA

    monkeypatch.setattr(rt, "_read_plan_ref", _plan)
    assert await rt.deploy_ref_vars(rt.ROLLBACK_PLAYBOOK) == {"deploy_ref": SHA, "deploy_is_rollback": "true"}


def test_a_stale_plan_does_not_pin_later_runs():
    now = datetime.now(timezone.utc)
    assert rt._plan_is_fresh({"created_at": (now - timedelta(minutes=5)).isoformat()}, 7200) is True
    assert rt._plan_is_fresh({"created_at": (now - timedelta(hours=3)).isoformat()}, 7200) is False
    assert rt._plan_is_fresh({"created_at": "not a date"}, 7200) is False
    assert rt._plan_is_fresh({}, 7200) is False
