# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Exactly one role may write autobot-chromadb.service (#13870).

Two ansible roles each shipped a template with the SAME unit name and different
`ExecStart` paths, and both wrote `/etc/systemd/system/autobot-chromadb.service`
unconditionally. Whichever role ran last won, so the deployed binary path, the
Description and the restart policy all flipped with run order.

Observed live during the #4090 investigation: a self-update applied the redis
role, which rewrote the unit underneath a running deployment and pointed it at a
different venv. #4090's outage was an `ExecStart` naming a venv that had no
chromadb in it — which template was in force decided whether the box worked, and
nothing in the deploy made that choice visible or deliberate.

Both roles are legitimate: they install chromadb for different topologies. The
defect is that ownership was implicit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_ANSIBLE = Path(__file__).resolve().parents[2] / "ansible"
_UNIT_DEST = "/etc/systemd/system/autobot-chromadb.service"
_ROLES = ("ai-stack", "redis")


def _template(role: str) -> Path:
    return _ANSIBLE / "roles" / role / "templates" / "autobot-chromadb.service.j2"


def _tasks_text(role: str) -> str:
    return (_ANSIBLE / "roles" / role / "tasks" / "code_only.yml").read_text(encoding="utf-8")


def test_both_roles_still_ship_a_template():
    """Guard the guard: if either template is renamed, every assertion below
    would pass against nothing."""
    for role in _ROLES:
        assert _template(role).is_file(), f"{role} no longer ships the unit template"


@pytest.mark.parametrize("role", _ROLES)
def test_the_unit_task_is_gated_on_ownership(role: str):
    """Both wrote the unit unconditionally — that is the defect."""
    text = _tasks_text(role)
    assert _UNIT_DEST in text, f"{role} no longer deploys the unit — this guard matches nothing"

    tasks = yaml.safe_load(text)
    deploying = [
        t for t in tasks if isinstance(t, dict) and (t.get("ansible.builtin.template") or {}).get("dest") == _UNIT_DEST
    ]
    assert len(deploying) == 1, f"{role} has {len(deploying)} tasks writing the unit"
    condition = deploying[0].get("when")
    assert condition, f"{role} writes {_UNIT_DEST} unconditionally — run order decides the ExecStart"
    assert "chromadb_service_owner" in str(condition), f"{role}'s gate does not reference the ownership variable"


@pytest.mark.parametrize("role", _ROLES)
def test_each_role_declares_a_default_owner(role: str):
    defaults = yaml.safe_load((_ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert "chromadb_service_owner" in defaults, f"{role} has no chromadb_service_owner default"
    assert defaults["chromadb_service_owner"] in _ROLES


def test_the_two_roles_agree_on_the_default():
    """Disagreeing defaults would deploy two units again, or none."""
    values = {
        role: yaml.safe_load((_ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8"))[
            "chromadb_service_owner"
        ]
        for role in _ROLES
    }
    assert len(set(values.values())) == 1, f"roles disagree on the default owner: {values}"


def test_the_ai_stack_only_topology_claims_ownership():
    """setup-ai-stack.yml has no redis role, so with the default it would deploy
    NO unit at all — a worse outcome than the flip this fixes."""
    play = yaml.safe_load((_ANSIBLE / "setup-ai-stack.yml").read_text(encoding="utf-8"))
    roles = {r["role"] if isinstance(r, dict) else r for r in play[0].get("roles", [])}
    assert "ai-stack" in roles and "redis" not in roles, "topology changed — revisit the ownership default"
    assert play[0].get("vars", {}).get("chromadb_service_owner") == "ai-stack"


def test_the_restart_policy_does_not_depend_on_which_role_won():
    """They differed — `always` vs `on-failure` — so the unit's FAILURE
    behaviour changed with role order, not just its path. #4090 was precisely
    about a unit restarting forever instead of reaching `failed`."""
    policies = {}
    for role in _ROLES:
        text = _template(role).read_text(encoding="utf-8")
        found = re.findall(r"^Restart=(\S+)", text, re.MULTILINE)
        assert found, f"{role}'s unit declares no Restart policy"
        policies[role] = found[0]
    assert len(set(policies.values())) == 1, f"restart policy differs between roles: {policies}"


def test_both_units_keep_the_4090_start_limit():
    """#4090: without these a unit whose ExecStart can never succeed restarts
    forever and never reaches `failed`. Both templates must keep them."""
    for role in _ROLES:
        text = _template(role).read_text(encoding="utf-8")
        assert "StartLimitIntervalSec=" in text, f"{role} lost its StartLimitIntervalSec (#4090)"
        assert "StartLimitBurst=" in text, f"{role} lost its StartLimitBurst (#4090)"
