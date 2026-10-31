# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One Ansible task file installs Grafana, and the updater reaches it (#19661).

Three copies pinned Grafana on a fresh install only, so a host provisioned earlier kept whatever
apt gave it. The monitoring role now holds the install; the other two callers include it.
"""

from __future__ import annotations

import re

import pytest
import yaml
from repo_tests._ansible_tasks import (
    ansible_yaml_files,
    eval_when,
    includes_tasks_file,
    installs_package,
    load_tasks,
    named,
)
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
    assert includes_tasks_file(yaml.safe_load((_ROOT / caller).read_text(encoding="utf-8")), "grafana_install.yml")


@pytest.mark.parametrize(
    ("task", "found"),
    [
        ({"ansible.builtin.include_tasks": "grafana_install.yml"}, True),
        ({"include_tasks": {"file": "grafana_install.yml"}}, True),
        ({"ansible.builtin.include_role": {"name": "monitoring", "tasks_from": "grafana_install.yml"}}, True),
        ({"block": [{"ansible.builtin.import_tasks": "grafana_install.yml"}]}, True),
        ({"ansible.builtin.debug": {"msg": "see grafana_install.yml"}}, False),
        ({"ansible.builtin.include_tasks": "other.yml"}, False),
        ({"vars": {"include_tasks": "grafana_install.yml"}}, False),
    ],
)
def test_only_an_executing_include_counts_as_reaching_it(task: dict, found: bool) -> None:
    assert includes_tasks_file([task], "grafana_install.yml") is found


@pytest.mark.parametrize(
    ("status", "present"),
    [
        ("install ok installed:11.1.0", True),
        ("install ok installed:2:12.0.0", True),
        ("deinstall ok config-files:11.1.0", False),
        ("", False),
    ],
)
def test_only_an_installed_package_reads_as_present(status: str, present: bool) -> None:
    """A package removed without --purge stays known to dpkg; the updater must not reinstall it."""
    facts = named(load_tasks(_ROOT / _HOME), "Note what the installed Grafana is")["ansible.builtin.set_fact"]
    expression = facts["_grafana_present"].strip("{} ")
    assert eval_when(expression, _grafana_installed={"stdout": status}) is present


@pytest.mark.parametrize(
    ("stdout", "version"),
    [("install ok installed:2:12.0.0", "2:12.0.0"), ("install ok installed:11.1.0~rc1", "11.1.0~rc1")],
)
def test_the_whole_debian_version_reaches_the_comparison(stdout: str, version: str) -> None:
    facts = named(load_tasks(_ROOT / _HOME), "Note what the installed Grafana is")["ansible.builtin.set_fact"]
    pattern, replacement = re.search(r"regex_replace\('(.+?)', '(.*?)'\)", facts["_grafana_current"]).groups()
    assert re.sub(pattern, replacement, stdout) == version


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
    assert "_grafana_compared.results[0].rc == 0" in gate
    compare = named(load_tasks(_ROOT / _HOME), "Compare the installed Grafana with grafana_version, by dpkg's rules")
    assert compare["ansible.builtin.command"]["argv"][:2] == ["dpkg", "--compare-versions"]
    assert [item["op"] for item in compare["loop"]] == ["lt", "gt"]
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


def test_the_upgrade_never_deletes_a_repo_file_and_waits_for_grafana_to_answer() -> None:
    """Displacing a source is the helper's job, which keeps a backup; health follows the migrating start."""
    outer = named(load_tasks(_ROOT / _HOME), "Install or upgrade Grafana")
    assert not [t for t in outer["block"] if t.get("ansible.builtin.file", {}).get("state") == "absent"]
    names = [task["name"] for task in outer["block"]]
    assert names.index("Upgrade with Grafana stopped") < names.index("Wait for Grafana to answer after the upgrade")


def test_the_database_copy_follows_the_configured_data_dir() -> None:
    assert "/var/lib/grafana" not in (_ROOT / _HOME).read_text(encoding="utf-8")


def test_yaml_discovery_reads_both_suffixes_and_nothing_else(tmp_path) -> None:
    for name in ("a.yml", "b.yaml", "c.j2", "d.yml.bak"):
        (tmp_path / name).write_text("[]\n", encoding="utf-8")
    assert [p.name for p in ansible_yaml_files(tmp_path)] == ["a.yml", "b.yaml"]
