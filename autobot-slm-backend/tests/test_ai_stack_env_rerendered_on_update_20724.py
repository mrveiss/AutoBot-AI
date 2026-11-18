# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20724: the builtin updater re-renders the AI Stack env files, from the one copy of the task."""

import pathlib

import yaml

_ANSIBLE = pathlib.Path(__file__).resolve().parents[1] / "ansible"
_TASKS = _ANSIBLE / "roles" / "ai-stack" / "tasks"
_ENV_DESTS = {"/etc/autobot/autobot-ai-stack.env", "{{ ai_install_dir }}/.env"}


def _tasks(name: str) -> list:
    return yaml.safe_load((_TASKS / name).read_text(encoding="utf-8"))


def _iter(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter(item)


def _env_renders(tasks: list) -> set:
    return {
        t["ansible.builtin.template"]["dest"]
        for t in _iter(tasks)
        if (t.get("ansible.builtin.template") or {}).get("src") == "ai-stack.env.j2"
    }


def _index(tasks: list, include: str) -> int:
    return next(i for i, t in enumerate(tasks) if t.get("ansible.builtin.include_tasks") == include)


def test_the_updater_reaches_both_env_renders() -> None:
    playbook = yaml.safe_load((_ANSIBLE / "playbooks" / "update-all-nodes.yml").read_text(encoding="utf-8"))
    applied = {
        (t["ansible.builtin.include_role"].get("tasks_from"))
        for t in _iter(playbook)
        if (t.get("ansible.builtin.include_role") or {}).get("name") == "ai-stack"
    }
    assert "code_only" in applied
    code_only = _tasks("code_only.yml")
    assert _index(code_only, "env_files.yml") >= 0
    assert _env_renders(_tasks("env_files.yml")) == _ENV_DESTS


def test_the_env_exists_before_the_unit_that_reads_it() -> None:
    code_only = _tasks("code_only.yml")
    unit = next(
        i
        for i, t in enumerate(code_only)
        if (t.get("ansible.builtin.template") or {}).get("src") == "autobot-ai-stack.service.j2"
    )
    assert _index(code_only, "env_files.yml") < unit


def test_there_is_one_copy_of_the_render() -> None:
    """A second copy in main.yml is how the update path lost the env in the first place."""
    assert _env_renders(_tasks("main.yml")) == set()
    assert _env_renders(_tasks("code_only.yml")) == set()
    main = _tasks("main.yml")
    start = next(
        i for i, t in enumerate(main) if (t.get("ansible.builtin.systemd") or {}).get("name") == "autobot-ai-stack"
    )
    assert _index(main, "code_only.yml") < start, "a fresh install renders the env before it starts the service"


def test_the_finder_sees_a_render() -> None:
    """Control: the empty set above means no render, not a finder that sees nothing."""
    sample = [{"ansible.builtin.template": {"src": "ai-stack.env.j2", "dest": "/x"}}]
    assert _env_renders(sample) == {"/x"}


def test_a_config_only_run_still_reaches_the_renders() -> None:
    """An include's tags gate the tasks under it: `--tags config` must pass both includes to reach env_files."""
    main = _tasks("main.yml")
    code_only = _tasks("code_only.yml")
    assert "config" in main[_index(main, "code_only.yml")]["tags"]
    assert "config" in code_only[_index(code_only, "env_files.yml")]["tags"]


def _named(tasks: list, needle: str) -> int:
    return next(i for i, t in enumerate(tasks) if needle in t.get("name", ""))


def _refuses(task: dict, password: str, rcs: list) -> bool:
    """Evaluate the refusal's `when` as Ansible would: every condition true."""
    import jinja2

    results = [{"rc": rc} if rc is not None else {"skipped": True} for rc in rcs]
    env = jinja2.Environment()
    variables = {"ai_redis_password": password, "_ai_env_redis_password_present": {"results": results}}
    return all(env.from_string("{{ " + c + " }}").render(**variables) == "True" for c in task["when"])


def test_an_empty_credential_is_never_rendered_over_a_real_one() -> None:
    """Every update re-renders now, so an unreadable SLM secret must stop the run, not strip Redis auth."""
    tasks = _tasks("env_files.yml")
    check, refuse = _named(tasks, "already carry a Redis password"), _named(tasks, "Refuse to write")
    renders = [
        i for i, t in enumerate(tasks) if (t.get("ansible.builtin.template") or {}).get("src") == "ai-stack.env.j2"
    ]
    assert check < refuse < min(renders)
    assert set(tasks[check]["loop"]) == _ENV_DESTS, "both rendered files are checked"
    assert "ansible.builtin.fail" in tasks[refuse]
    assert _refuses(tasks[refuse], "", [0, 1]), "no credential to render, and a file has one: stop"
    assert not _refuses(tasks[refuse], "", [1, 1]), "neither file has one (fresh install): render"
    assert not _refuses(tasks[refuse], "pw-sample", [None, None]), "a credential to render: render"
    assert not _refuses(tasks[refuse], "", [None, None]), "control: skipped checks never refuse"
    assert _refuses(tasks[refuse], "", [2, 1]), "a file that exists but can't be read: fail closed"


def test_the_probe_tells_absent_from_unreadable(tmp_path) -> None:
    """The task's own argv: absent is 1, a password is 0, a file it can't read is 2 (and refuses, above)."""
    import os
    import subprocess  # nosec B404 -- runs the task's own probe on temporary files

    argv = _tasks("env_files.yml")[_named(_tasks("env_files.yml"), "already carry a Redis password")]
    argv = argv["ansible.builtin.command"]["argv"]
    has, without, locked = tmp_path / "has.env", tmp_path / "without.env", tmp_path / "locked.env"
    has.write_text("REDIS_PASSWORD=x\n", encoding="utf-8")
    without.write_text("OTHER=1\n", encoding="utf-8")
    locked.write_text("REDIS_PASSWORD=x\n", encoding="utf-8")
    locked.chmod(0)

    def rc(path) -> int:
        command = [part if part != "{{ item }}" else str(path) for part in argv]
        return subprocess.run(command, capture_output=True, check=False).returncode  # nosec B603

    assert (rc(tmp_path / "absent.env"), rc(has), rc(without)) == (1, 0, 1)
    if os.geteuid() != 0:  # root reads a mode-0 file, so the unreadable case only exists for others
        assert rc(locked) == 2
