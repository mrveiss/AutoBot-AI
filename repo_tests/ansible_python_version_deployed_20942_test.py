# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20942: .python-version must be deployed to the install root.

autobot_shared/python_floor.py reads ``<install root>/.python-version``; without a
task that copies it there every startup logs "unreadable" and uses the fallback.
The updater ships it inside the shared archive built from ``deploy_ref`` (so every play
that unpacks autobot_shared carries it, before any restart); the roles that stage it by
``copy`` must read it from the checkout the shared code comes from.
"""

import copy as _copy
from pathlib import Path

import yaml
from repo_tests._ansible_restart_unit import restarts_unit
from repo_tests._paths import repo_root

_ROOT = repo_root()
_ANSIBLE = _ROOT / "autobot-slm-backend" / "ansible"
_ROLE = _ANSIBLE / "roles" / "_shared" / "tasks" / "stage_shared_manifests.yml"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_AGENT = _ANSIBLE / "roles" / "_shared" / "tasks" / "install_agent_autobot_shared.yml"
_DEST = "{{ autobot.base_dir }}/.python-version"
_ROLE_ROOT = "code_source_dir"
_AGENT_ROOT = "shared_parent"


def _tasks(node) -> list[dict]:
    out: list[dict] = []
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict):
                out.append(item)
                for key in ("block", "rescue", "always", "tasks"):
                    out.extend(_tasks(item.get(key)))
    return out


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _is_staging(task: dict, root: str) -> bool:
    """A copy that can run, whose source is under ``root`` (the deployed checkout)."""
    cp = task.get("ansible.builtin.copy") or task.get("copy")
    return (
        isinstance(cp, dict)
        and str(cp.get("src", "")).endswith("/.python-version")
        and root in str(cp.get("src", ""))
        and str(cp.get("dest", "")) == _DEST
        and task.get("when", True) not in (False, "false", "False")
    )


def _stages_from_deploy_ref(tasks: list[dict]) -> bool:
    """A runnable ``git show <deploy_ref>:.python-version`` followed by a copy of its stdout.

    Reading the checkout's working tree (a ``copy`` with a ``src`` under the checkout) is
    wrong: a checkout that is not at deploy_ref would overwrite the archive's copy.
    """
    reads = [
        i
        for i, t in enumerate(tasks)
        if isinstance((c := t.get("ansible.builtin.command") or t.get("command")), dict)
        and "show" in (c.get("argv") or [])
        and any("deploy_ref" in str(a) and str(a).endswith(":.python-version") for a in c["argv"])
        and t.get("register")
        and t.get("delegate_to") == "localhost"
        and t.get("when", True) not in (False, "false", "False")
    ]
    for i in reads:
        reg = tasks[i]["register"]
        for t in tasks[i + 1 :]:
            cp = t.get("ansible.builtin.copy") or t.get("copy")
            if (
                isinstance(cp, dict)
                and "src" not in cp
                and str(cp.get("dest", "")) == _DEST
                and reg in str(cp.get("content", ""))
                and t.get("when", True) not in (False, "false", "False")
            ):
                return True
    return False


def role_stages_from_deploy_ref(path: Path) -> bool:
    return _stages_from_deploy_ref(_tasks(_load(path)))


def _deploys_shared(task: dict) -> bool:
    un = task.get("unarchive") or task.get("ansible.builtin.unarchive")
    return isinstance(un, dict) and str(un.get("src", "")).endswith("/shared.tar.gz")


def deploys_python_version(path: Path, root: str) -> bool:
    """True if a runnable copy task in ``path`` lands ``.python-version`` from ``root``."""
    return any(_is_staging(t, root) for t in _tasks(_load(path)))


def archive_carries_floor(plays: list[dict]) -> bool:
    """True if the shared archive built from deploy_ref includes ``.python-version``."""
    for task in _tasks(plays[0].get("tasks")):
        for item in task.get("loop") or []:
            if isinstance(item, dict) and item.get("name") == "shared":
                return {"autobot_shared/", ".python-version"} <= set(str(item.get("path")).split())
    return False


def _restart_index(tasks: list[dict], name: str | None = "autobot-slm-backend") -> int:
    """Index of the first restart (of ``name``, or of any unit when None), either shape."""
    for i, t in enumerate(tasks):
        if restarts_unit(t, name):
            return i
    raise AssertionError("no restart task found")


def unpacks_before_restart(play: dict, name: str | None = "autobot-slm-backend") -> bool:
    tasks = _tasks(play.get("tasks"))
    deploys = [i for i, t in enumerate(tasks) if _deploys_shared(t)]
    return bool(deploys) and min(deploys) < _restart_index(tasks, name)


def _slm_play(plays: list[dict]) -> dict:
    return next(p for p in plays if p.get("hosts") == "slm_server")


def test_source_file_exists():
    assert (_ROOT / ".python-version").is_file()


def test_role_stages_python_version_from_deploy_ref():
    assert role_stages_from_deploy_ref(_ROLE), f"{_ROLE.name}: no #20942 staging from deploy_ref"


def test_agent_install_stages_python_version_from_the_shared_tree():
    assert deploys_python_version(_AGENT, _AGENT_ROOT), f"{_AGENT.name}: no #20942 staging from shared_parent"


def test_playbook_has_shared_deploying_plays():
    shared_plays = [p for p in _load(_PLAYBOOK) if any(_deploys_shared(t) for t in _tasks(p.get("tasks")))]
    assert len(shared_plays) >= 2, "expected the SLM and infrastructure plays to deploy autobot_shared"


def test_shared_archive_carries_python_version_from_deploy_ref():
    assert archive_carries_floor(_load(_PLAYBOOK))


def test_slm_play_unpacks_shared_before_the_backend_restart():
    assert unpacks_before_restart(_slm_play(_load(_PLAYBOOK)))


def _infra_play(plays: list[dict]) -> dict:
    return next(p for p in plays if p.get("hosts") == "infrastructure")


def test_infrastructure_play_unpacks_shared_before_any_restart():
    assert unpacks_before_restart(_infra_play(_load(_PLAYBOOK)), None)


def test_control_infrastructure_restart_before_unpack_is_detected():
    play = _copy.deepcopy(_infra_play(_load(_PLAYBOOK)))
    tasks = play["tasks"]
    tasks.insert(0, tasks.pop(_restart_index(tasks, None)))
    assert not unpacks_before_restart(play, None)


def test_control_archive_without_python_version_is_detected():
    plays = _copy.deepcopy(_load(_PLAYBOOK))
    for task in _tasks(plays[0].get("tasks")):
        for item in task.get("loop") or []:
            if isinstance(item, dict) and item.get("name") == "shared":
                item["path"] = "autobot_shared/"
    assert not archive_carries_floor(plays)


def test_control_restart_before_unpack_is_detected():
    play = _copy.deepcopy(_slm_play(_load(_PLAYBOOK)))
    tasks = play["tasks"]
    restart = tasks.pop(_restart_index(tasks))
    tasks.insert(0, restart)
    assert not unpacks_before_restart(play)


_TASK = "- ansible.builtin.copy:\n    src: '{{ %s }}/.python-version'\n    dest: '%s'\n%s"


def _write(tmp_path, root: str, extra: str = "", dest: str = _DEST) -> Path:
    path = tmp_path / "x.yml"
    path.write_text(_TASK % (root, dest, extra), encoding="utf-8")
    return path


def test_control_detector_accepts_a_qualifying_task(tmp_path):
    assert deploys_python_version(_write(tmp_path, _ROLE_ROOT), _ROLE_ROOT)


def test_control_detector_rejects_a_file_without_the_task(tmp_path):
    other = tmp_path / "x.yml"
    other.write_text(
        "- ansible.builtin.copy:\n    src: a/constraints/shared.txt\n    dest: '{{ autobot.base_dir }}/c'\n",
        encoding="utf-8",
    )
    assert not deploys_python_version(other, _ROLE_ROOT)


def test_control_detector_rejects_a_copy_from_another_checkout(tmp_path):
    assert not deploys_python_version(_write(tmp_path, "playbook_dir"), _ROLE_ROOT)


def test_control_detector_rejects_a_task_that_can_never_run(tmp_path):
    assert not deploys_python_version(_write(tmp_path, _ROLE_ROOT, "  when: false\n"), _ROLE_ROOT)


def test_control_working_tree_read_fails_the_guard():
    """A staging copy whose src sits under the checkout (no ref) is the #20942 finding."""
    tasks = _tasks(_load(_ROLE))
    assert _stages_from_deploy_ref(tasks)
    mutated = _copy.deepcopy(tasks)
    for t in mutated:
        cp = t.get("ansible.builtin.copy")
        if isinstance(cp, dict) and cp.get("dest") == _DEST:
            cp.pop("content")
            cp["src"] = "{{ code_source_dir }}/.python-version"
    assert not _stages_from_deploy_ref(mutated)


def test_control_read_without_a_ref_fails_the_guard():
    mutated = _copy.deepcopy(_tasks(_load(_ROLE)))
    for t in mutated:
        c = t.get("ansible.builtin.command")
        if isinstance(c, dict):
            c["argv"] = [a for a in c["argv"] if "deploy_ref" not in str(a)] + ["HEAD:.python-version"]
    assert not _stages_from_deploy_ref(mutated)
