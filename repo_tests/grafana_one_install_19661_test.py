# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One Ansible task file installs Grafana, and the updater reaches it (#19661).

Three copies pinned Grafana on a fresh install only, so a host provisioned earlier kept whatever
apt gave it. The monitoring role now holds the install; the other two callers include it.
"""

from __future__ import annotations

import pytest
import yaml
from repo_tests._ansible_tasks import ansible_yaml_files, installs_package, load_tasks, named, without_comment_lines
from repo_tests._paths import repo_root

_ROOT = repo_root()
_ANSIBLE = _ROOT / "autobot-slm-backend/ansible"
_HOME = "autobot-slm-backend/ansible/roles/monitoring/tasks/grafana_install.yml"
_CALLERS = (
    "autobot-slm-backend/ansible/roles/monitoring/tasks/grafana.yml",
    "autobot-slm-backend/ansible/roles/slm_manager/tasks/grafana.yml",
    "autobot-slm-backend/ansible/migrate-grafana-to-vm.yml",
    "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml",
)


def _documents() -> dict[str, object]:
    found = {}
    for path in ansible_yaml_files(_ANSIBLE):
        try:
            found[path.relative_to(_ROOT).as_posix()] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # a vault-tagged inventory file holds no tasks
            continue
    return found


def test_only_the_monitoring_role_installs_grafana() -> None:
    documents = _documents()
    assert len(documents) > 100, f"only {len(documents)} files parsed; an empty sweep finds nothing"
    assert {rel for rel, doc in documents.items() if installs_package(doc, "grafana")} == {_HOME}


@pytest.mark.parametrize("caller", _CALLERS)
def test_each_caller_reaches_the_one_install(caller: str) -> None:
    assert "grafana_install.yml" in without_comment_lines((_ROOT / caller).read_text(encoding="utf-8"))


def _updater_grafana_plays() -> list[dict]:
    text = (_ROOT / "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml").read_text(encoding="utf-8")
    return [
        play
        for play in yaml.safe_load(text)
        if any("grafana_install" in str(task.get("ansible.builtin.include_role")) for task in play.get("tasks", []))
    ]


def test_the_updater_upgrades_only_a_grafana_that_is_there() -> None:
    """A host without Grafana stays without it; every host that runs one is in the play."""
    play = _updater_grafana_plays()
    assert len(play) == 1
    assert set(play[0]["hosts"].split(":")) == {"slm_server", "monitoring_vm"}
    task = next(t for t in play[0]["tasks"] if "ansible.builtin.include_role" in t)
    assert task["vars"]["grafana_fresh_install"] is False
    assert task["ansible.builtin.include_role"]["apply"]["become"] is True


def test_the_install_never_downgrades_and_the_updater_never_adds_one() -> None:
    gate = named(load_tasks(_ROOT / _HOME), "Install or upgrade Grafana")["when"][1]
    assert "_grafana_current is version(grafana_version, '<')" in gate
    assert "not (_grafana_present | bool) and (grafana_fresh_install | default(true) | bool)" in gate
    assert "allow_downgrade" not in (_ROOT / _HOME).read_text(encoding="utf-8")


def test_the_database_copy_comes_after_the_stop_and_grafana_comes_back() -> None:
    outer = named(load_tasks(_ROOT / _HOME), "Install or upgrade Grafana")
    upgrade = named(outer["block"], "Upgrade with Grafana stopped")
    names = [task["name"] for task in upgrade["block"]]
    assert (
        names.index("Stop Grafana before the upgrade")
        < names.index("Keep a copy of the Grafana database from before the upgrade")
        < names.index("Install Grafana")
    )
    assert upgrade["always"][0]["ansible.builtin.systemd"]["state"] == "started"
