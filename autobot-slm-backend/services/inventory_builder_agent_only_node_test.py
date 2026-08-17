# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A node whose only role is slm-agent must still reach a play (#14336).

`api/nodes.py` deliberately never removes `slm-agent` from a node's role list
("Remove roles no longer assigned (except slm-agent — always keep)"), so a
node whose functional roles are all unassigned legitimately ends up with
`roles=["slm-agent"]` and nothing else.

Before this fix that node received ZERO tasks from `update-all-nodes.yml`:

* Play 1 (`hosts: slm_server`) skips it — correct, and #14330's fix.
* Play 2 (`hosts: infrastructure`) also skipped it, because `has_app_roles`
  is deliberately false for every `slm-`-prefixed token (#11453), so the node
  never joined `infrastructure` either.

`groups_for_role_tokens` now also routes a node into `infrastructure` when
its role set carries the agent but nothing `_ROLE_TO_GROUPS` recognises as an
app component and it is not the manager. Every other Play 2 task stays gated
on its own group (`'backend' in group_names`, `'npu' in group_names`, ...),
so this adds nothing beyond the agent-redeploy task, which is gated only on
`slm_node_id is defined` — true for every node.

Verification bar (per the issue): the invariant is "a node with *any* single
role receives the tasks that role owns", not just that slm-agent specifically
now works — a guard covering only the reported role would be narrower than
its own subject. `test_every_single_role_reaches_a_targetable_play` checks
that generally, parsed off the live playbook rather than a hardcoded set, so
it also would have caught the original defect (slm-agent/slm_agent were the
only two entries that failed it).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PLAYBOOK = _BACKEND_ROOT / "ansible" / "playbooks" / "update-all-nodes.yml"


def _load():
    spec = importlib.util.spec_from_file_location("_ib_14336", _BACKEND_ROOT / "services" / "inventory_builder.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_ib_14336"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("_ib_14336", None)
    return module


_ib = _load()

_INFRASTRUCTURE = "infrastructure"


@pytest.mark.parametrize("roles", [["slm-agent"], ["slm_agent"], ["slm-agent", "slm_agent"]])
def test_an_agent_only_node_reaches_play_2(roles):
    """The reported case: an agent-only node must join `infrastructure`.

    Play 1 (`slm_server`) still correctly excludes it (#14330) — this only
    asserts the node is not orphaned from *every* play.
    """
    groups = _ib.groups_for_role_tokens(roles)

    assert _INFRASTRUCTURE in groups, (
        f"roles {roles} leave the node out of every group update-all-nodes.yml "
        "targets — it receives zero tasks (#14336)"
    )
    assert "slm_server" not in groups, "an agent-only node must still not become the manager (#14330)"


def test_an_agent_plus_unrecognised_role_still_reaches_play_2():
    """An agent node also carrying a role `_ROLE_TO_GROUPS` does not recognise
    must not be silently dropped either — the unrecognised token contributes
    no group, so the node is agent-only in every way that matters here."""
    groups = _ib.groups_for_role_tokens(["some-future-role-not-yet-mapped", "slm-agent"])

    assert _INFRASTRUCTURE in groups


def _play_target_groups() -> set[str]:
    """Every group a play in update-all-nodes.yml is gated on, `localhost` excluded.

    Parsed off the live playbook (not hardcoded) so a future play addition or
    rename is picked up automatically instead of silently narrowing the check.
    """
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    groups: set[str] = set()
    for play in playbook:
        host = play.get("hosts") if isinstance(play, dict) else None
        if isinstance(host, str) and host != "localhost":
            groups.add(host)
    return groups


#: One representative single-role token per `_ROLE_TO_GROUPS` entry (plus the
#: exact-keyed `slm_agent` underscore form). Each is asserted alone — a real
#: node carries more, but the invariant must hold for the minimal case.
_SINGLE_ROLE_TOKENS = [
    "slm-backend",
    "slm-frontend",
    "slm-agent",
    "slm_agent",
    "backend",
    "celery",
    "scheduler",
    "autobot_shared",
    "frontend",
    "npu-worker",
    "npu_worker",
    "ai-stack",
    "chromadb",
    "autobot-llm-cpu",
    "tts-worker",
    "redis",
    "postgres",
    "slm-database",
    "browser-service",
    "monitoring",
    "slm-monitoring",
]


@pytest.mark.parametrize("role", _SINGLE_ROLE_TOKENS)
def test_every_single_role_reaches_a_targetable_play(role):
    """Every recognised single role must land the node in a group some play
    in update-all-nodes.yml is gated on — never in a group nothing targets.

    This is the general form of the #14336 invariant: it does not special-case
    slm-agent, so it would have failed for slm-agent/slm_agent before the fix
    exactly as it now passes for every other recognised role.
    """
    groups = _ib.groups_for_role_tokens([role])
    targetable = _play_target_groups()

    assert groups & targetable, (
        f"role {role!r} alone resolves to {sorted(groups)}, none of which "
        f"update-all-nodes.yml targets ({sorted(targetable)}) — the node "
        "receives zero tasks"
    )
