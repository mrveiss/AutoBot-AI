# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The builtin updater applies the postgresql role's server config on every host that runs it (#19848).

PR #19421 fixed postgresql_listen_addresses in the role, and an updated host kept listening on
every interface: update-all-nodes.yml included roles/postgresql only for credentials_reconcile,
never the task that renders postgresql.conf. config_file.yml is now that task's one home, used
by configure.yml on install and by the updater on every Code Sync.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_UPDATER = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_ROLE_TASKS = _ANSIBLE / "roles" / "postgresql" / "tasks"


def _includes(play: dict, role: str) -> list[str]:
    """tasks_from values of every include_role of *role* in *play*'s tasks."""
    out = []
    for task in play.get("tasks", []) or []:
        inc = task.get("ansible.builtin.include_role") or task.get("include_role")
        if isinstance(inc, dict) and inc.get("name") == role:
            out.append(inc.get("tasks_from", "main"))
    return out


def _plays() -> dict[str, dict]:
    return {p["hosts"]: p for p in yaml.safe_load(_UPDATER.read_text(encoding="utf-8")) if "hosts" in p}


def test_every_play_that_touches_postgresql_renders_postgresql_conf():
    """A play including any postgresql task file reaches a PostgreSQL host, so it renders the config too."""
    plays = _plays()
    touching = {hosts for hosts, play in plays.items() if _includes(play, "postgresql")}
    assert {"slm_server", "infrastructure", "database"} <= touching, f"plays including postgresql: {sorted(touching)}"
    missing = sorted(hosts for hosts in touching if "config_file" not in _includes(plays[hosts], "postgresql"))
    assert not missing, f"plays on {missing} include postgresql but never render postgresql.conf"


def test_postgresql_conf_has_one_home():
    """configure.yml includes config_file.yml rather than carrying its own copy of the template task."""
    configure = (_ROLE_TASKS / "configure.yml").read_text(encoding="utf-8")
    assert "config_file.yml" in configure and "postgresql.conf.j2" not in configure
    assert "postgresql.conf.j2" in (_ROLE_TASKS / "config_file.yml").read_text(encoding="utf-8")


def test_contrast_a_credentials_only_include_is_caught():
    play = {"tasks": [{"ansible.builtin.include_role": {"name": "postgresql", "tasks_from": "credentials_reconcile"}}]}
    assert "config_file" not in _includes(play, "postgresql")
