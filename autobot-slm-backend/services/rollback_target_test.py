# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A rollback's deploy ref is carried to the playbook only while the rollback is in flight (#20214)."""

from __future__ import annotations

import asyncio

import pytest

from services import rollback_target as rt

SHA = "a" * 40


async def test_nothing_is_added_outside_a_rollback():
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


async def test_after_the_scope_ends_the_next_run_deploys_main_again():
    with rt.rollback_scope(SHA):
        pass
    assert await rt.deploy_ref_vars(rt.ROLLBACK_PLAYBOOK) == {}


@pytest.mark.parametrize("bad", ["main", "--output=x", "A" * 40, "a" * 39, "", None, "a" * 40 + "\n"])
def test_only_a_full_lowercase_commit_id_can_be_a_target(bad):
    assert rt.is_full_sha(bad) is False
    with pytest.raises(ValueError):
        with rt.rollback_scope(bad):
            pass


def test_deploy_ref_vars_has_no_stored_plan_reader():
    """A playbook run never consults the stored plan, so an unrelated sync cannot inherit a rollback's commit."""
    assert not hasattr(rt, "_read_plan_ref")


def test_an_ordinary_plan_resumes_without_a_ref():
    assert rt.resume_ref({"version": 2, "deploy_ref": None, "is_rollback": False}) is None
    assert rt.resume_ref({"version": 2}) is None


def test_a_rollback_plan_resumes_with_its_ref():
    assert rt.resume_ref({"deploy_ref": SHA, "is_rollback": True}) == SHA
    assert rt.resume_ref({"deploy_ref": SHA}) == SHA


@pytest.mark.parametrize("ref", [None, "", "main", "--output=x", "A" * 40, "a" * 39, 12345])
def test_a_rollback_plan_without_a_valid_ref_is_refused(ref):
    with pytest.raises(rt.ResumeRefInvalid):
        rt.resume_ref({"deploy_ref": ref, "is_rollback": True})


@pytest.mark.parametrize("ref", ["main", "A" * 40, ""])
def test_a_plan_carrying_only_a_bad_ref_is_refused(ref):
    with pytest.raises(rt.ResumeRefInvalid):
        rt.resume_ref({"deploy_ref": ref})


async def test_the_resumed_scope_binds_the_ref_for_the_stage_and_releases_it():
    with rt.resumed_scope(SHA):
        assert await rt.deploy_ref_vars(rt.ROLLBACK_PLAYBOOK) == {"deploy_ref": SHA, "deploy_is_rollback": "true"}
    assert await rt.deploy_ref_vars(rt.ROLLBACK_PLAYBOOK) == {}
    with rt.resumed_scope(None):
        assert await rt.deploy_ref_vars(rt.ROLLBACK_PLAYBOOK) == {}
