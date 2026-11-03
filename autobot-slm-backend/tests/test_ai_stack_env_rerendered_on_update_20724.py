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
