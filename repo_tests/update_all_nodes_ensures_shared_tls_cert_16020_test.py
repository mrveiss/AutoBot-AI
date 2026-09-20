# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The update path ensures the shared TLS keypair on every node that needs it (#16020, 2026-09-14 addendum).

A fleet node carrying only `slm-agent` + `vnc` had nginx failed for two days:

    nginx -t: [emerg] cannot load certificate "/etc/autobot/certs/server-cert.pem":
              No such file or directory

`tls_cert_consumers_provision_it_16020_test.py` proved every ROLE that reads the
shared keypair also ensures it exists. That does not reach this node, because
`update-all-nodes.yml` -- the playbook behind code-sync / self-update, the ONLY
path a GUI user reaches -- runs no roles in its infrastructure/database plays
for `vnc`, and applies `roles/redis` only via `tasks_from: code_only`, which
skips the role's own `tasks/main.yml` entirely. A node maintained only through
this playbook could never repair a missing cert for either.

Worse, `group_names` itself cannot see the vnc node's need: `vnc` has no entry
in `services/inventory_builder.py::_ROLE_TO_GROUPS` (the map this playbook's
dynamic inventory groups are built from) -- it reaches an ansible group only
through the separate, legacy `role_registry.ROLE_ANSIBLE_GROUPS` mapping that
only `provision-fleet-roles.yml` consults. So a `'vnc' in group_names` gate
would silently exempt exactly the node this issue was filed for. The correct
signal is the `role_vnc_active` fact in `inventory/group_vars/all.yml`, computed
from the raw `node_roles` hostvar independently of ansible-group membership.
Backend and frontend keep their existing `group_names` gate (#16522/#16566) --
that route already works for them; only vnc needed the fact instead.

This guard reads `update-all-nodes.yml` as text (parsing it as an Ansible
playbook would need a live inventory + facts this repo cannot supply).
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_PLAYBOOK = repo_root() / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml"
_SHARED_TASK = "ensure_node_tls_cert.yml"
_INCLUDE_LINE = f'include_tasks: "../_shared/tasks/{_SHARED_TASK}"'

_PLAY_HEADER = re.compile(r'\n- name: "Play ')
_TASK_HEADER = re.compile(r'\n    - name: "')

_INVENTORY_BUILDER = repo_root() / "autobot-slm-backend" / "services" / "inventory_builder.py"


def _play_text(play_name_prefix: str) -> str:
    """Slice out one play's own text, bounded by the next play header.

    Sliced rather than matched against the whole file so a `when:` string in a
    DIFFERENT play (Play 1's SLM-only components, Play 3's cleanup) can never
    satisfy an assertion meant for the play that actually reaches this node.
    """
    text = _PLAYBOOK.read_text(encoding="utf-8")
    start = text.index(f'- name: "{play_name_prefix}')
    tail = text[start + 1 :]
    next_play = _PLAY_HEADER.search(tail)
    end = start + 1 + next_play.start() if next_play else len(text)
    return text[start:end]


def _task_block(play_text: str, task_name: str) -> str:
    """One task's own text within a play, `when:` included, found by its exact name."""
    header = play_text.index(f'- name: "{task_name}"')
    next_task = _TASK_HEADER.search(play_text, header + 1)
    end = next_task.start() if next_task else len(play_text)
    return play_text[header:end]


def test_the_derivation_finds_both_plays_and_the_shared_task():
    """A derivation that finds nothing would make every assertion below vacuous."""
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} is gone -- this guard is pinned to the wrong path"
    play2 = _play_text("Play 2 - Update Other Infrastructure Nodes")
    play2b = _play_text("Play 2b - Update Database Nodes")
    assert "hosts: infrastructure" in play2, "Play 2 no longer targets `infrastructure`"
    assert "hosts: database" in play2b, "Play 2b no longer targets `database`"
    assert play2.count(_INCLUDE_LINE) >= 3, "expected Backend, Frontend and VNC to each include the shared task"


def test_play_two_ensures_the_keypair_for_a_vnc_only_node():
    """The VNC node the issue was filed for: no backend, no frontend, only vnc."""
    play2 = _play_text("Play 2 - Update Other Infrastructure Nodes")
    task = _task_block(play2, "[PLAY 2] VNC | Ensure the shared node TLS cert")
    assert _INCLUDE_LINE in task, "the VNC task does not include the shared TLS cert task (#16020)"
    assert "role_vnc_active" in task, (
        "the VNC task must gate on the role_vnc_active FACT, not group_names -- "
        "vnc has no _ROLE_TO_GROUPS entry, so a group_names gate would silently "
        "exempt exactly the node #16020 was filed for"
    )
    # Must run before SOME later task in the play, proving it is reachable and
    # not dead code appended after the play's own tasks list ends.
    frontend_deploy = play2.index('"[PLAY 2] Frontend | Deploy autobot-frontend"')
    assert play2.index(task) < frontend_deploy, "the VNC TLS-ensure task must run inside the play, not after it"


def test_play_two_b_ensures_the_keypair_for_redis():
    """Play 2b applies `roles/redis` only via `tasks_from: code_only`, which
    does NOT include the shared task (that lives only in the role's
    `tasks/main.yml`, the full-provisioning entrypoint) -- so a database node
    maintained only through this play has the identical gap as the vnc node.
    """
    play2b = _play_text("Play 2b - Update Database Nodes")
    task = _task_block(play2b, "[PLAY 2b] Database | Ensure the shared node TLS cert")
    assert _INCLUDE_LINE in task, "Play 2b never ensures the shared TLS keypair for redis (#16020)"
    assert "role_redis_active" in task, "Play 2b's TLS-ensure task does not gate on role_redis_active (#16020)"
    deploy_task = play2b.index('"[PLAY 2b] Database | Deploy role-owned service files (#13535)"')
    assert play2b.index(task) < deploy_task, "the TLS-ensure task must run before the redis service-file deploy"


def _role_to_groups_block() -> str:
    """The `_ROLE_TO_GROUPS` dict literal's own text, brace-matched.

    Read as text, not imported: `autobot-backend` and `autobot-slm-backend`
    both define a top-level `services` package (#13084), and `repo_tests` is
    collected together with `autobot-backend` in CI's two-invocation split
    (see `pytest.ini`) -- a bare `from services.inventory_builder import ...`
    here would resolve `services` to the WRONG backend, if it resolved at all.
    """
    text = _INVENTORY_BUILDER.read_text(encoding="utf-8")
    start = text.index("_ROLE_TO_GROUPS: dict[str, frozenset] = {")
    depth = 0
    for offset, char in enumerate(text[start:]):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : start + offset + 1]
    raise AssertionError("_ROLE_TO_GROUPS dict literal never closes -- brace matching is wrong")


def test_vnc_has_no_group_names_route_so_the_fact_gate_is_load_bearing():
    """The known positive: prove the failure mode this guard exists to catch.

    If `vnc` ever gained an entry in `_ROLE_TO_GROUPS`, a bare
    `'vnc' in group_names` gate would start working too, and this guard would
    stop being able to tell the difference between "gated correctly" and
    "gated by luck". Pinning the absence keeps `role_vnc_active` demonstrably
    necessary, not just sufficient.
    """
    block = _role_to_groups_block()
    assert re.search(r'"vnc"\s*:', block) is None, (
        "vnc now has a _ROLE_TO_GROUPS entry -- re-verify whether "
        "update-all-nodes.yml's TLS-ensure gate still needs role_vnc_active "
        "specifically, or whether a group_names gate would now also work"
    )
