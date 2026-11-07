# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A template one role borrows from another must render in the BORROWING role's scope.

Role defaults are not shared across roles. When ``slm_agent`` renders
``roles/monitoring/templates/node_exporter.service.j2``, only slm_agent's own
defaults/vars and the inventory ``group_vars/all.yml`` are in scope -- not the
monitoring role's defaults. #18556 made that template read ``monitoring_listen_address``,
declared only in monitoring's defaults, and every co-located slm-agent update then
failed with ``AnsibleUndefinedVariable`` at the node_exporter step.

This renders every cross-role ``template: src: ../../<role>/templates/...`` with
``StrictUndefined`` against exactly the variables the borrowing play can see, so an
undeclared variable fails here instead of on a host.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import jinja2.meta
import pytest
import yaml

_ANSIBLE = Path(__file__).resolve().parents[1]
_ROLES = _ANSIBLE / "roles"
_GROUP_VARS_ALL = _ANSIBLE / "inventory" / "group_vars" / "all.yml"
_CROSS_ROLE_SRC = re.compile(r"^\.\./\.\./(?P<role>[^/]+)/templates/(?P<name>.+)$")
#: Facts and magic vars Ansible supplies at run time; a template may read them freely.
_RUNTIME_PREFIXES = ("ansible_", "inventory_hostname", "groups", "hostvars", "item")


def _yaml(path: Path) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.is_file() else {}


#: Keys whose value is a nested task list (#18951): a template inside them is still a task.
_NESTED_TASK_KEYS = ("block", "rescue", "always")


def _walk_tasks(tasks: list | None):
    """Every task in *tasks*, descending into block/rescue/always at any depth."""
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        yield task
        for key in _NESTED_TASK_KEYS:
            yield from _walk_tasks(task.get(key))


def _template_src(task: dict) -> str:
    spec = task.get("ansible.builtin.template") or task.get("template")
    return str(spec.get("src", "")) if isinstance(spec, dict) else ""


def _cross_role_templates() -> list[tuple[str, str, Path]]:
    """(borrowing role, task file, borrowed template path) for every cross-role template task."""
    found = []
    for task_file in sorted(_ROLES.glob("*/tasks/*.yml")):
        role = task_file.parent.parent.name
        for task in _walk_tasks(yaml.safe_load(task_file.read_text(encoding="utf-8"))):
            match = _CROSS_ROLE_SRC.match(_template_src(task))
            if match and match["role"] != role:
                found.append((role, task_file.name, _ROLES / match["role"] / "templates" / match["name"]))
    return found


def _scope(role: str) -> dict:
    """What a play running ``role`` sees: group_vars/all, then the role's own defaults and vars."""
    scope = dict(_yaml(_GROUP_VARS_ALL))
    scope.update(_yaml(_ROLES / role / "defaults" / "main.yml"))
    scope.update(_yaml(_ROLES / role / "vars" / "main.yml"))
    return scope


def _undeclared(template: Path, scope: dict) -> set[str]:
    env = jinja2.Environment()
    names = jinja2.meta.find_undeclared_variables(env.parse(template.read_text(encoding="utf-8")))
    return {n for n in names if n not in scope and not n.startswith(_RUNTIME_PREFIXES)}


def test_there_is_at_least_one_cross_role_template_to_check() -> None:
    """Not vacuous: the slm_agent -> monitoring node_exporter borrow is the known instance."""
    assert ("slm_agent", "node_exporter.yml") in {(r, t) for r, t, _ in _cross_role_templates()}


@pytest.mark.parametrize(("role", "task_file", "template"), _cross_role_templates(), ids=lambda v: str(v))
def test_a_borrowed_template_renders_in_the_borrowing_roles_scope(role: str, task_file: str, template: Path) -> None:
    missing = _undeclared(template, _scope(role))
    assert not missing, (
        f"{role}/tasks/{task_file} renders {template.relative_to(_ROLES)}, which reads {sorted(missing)} -- "
        f"not declared in group_vars/all.yml nor in {role}'s defaults/vars. Declare shared vars in group_vars/all.yml."
    )


def test_contrast_a_variable_only_the_owning_role_declares_is_caught(tmp_path: Path) -> None:
    """The #18556 shape: the borrowed template reads a var only the template's own role declares."""
    template = tmp_path / "borrowed.j2"
    template.write_text("--listen={{ owner_only_var }}:{{ node_exporter_port }}", encoding="utf-8")
    assert _undeclared(template, {"node_exporter_port": 9100}) == {"owner_only_var"}
    assert _undeclared(template, {"node_exporter_port": 9100, "owner_only_var": "0.0.0.0"}) == set()


def test_contrast_a_template_nested_in_block_rescue_always_is_found() -> None:
    """#18951: templates inside block/rescue/always are tasks too and must be walked."""
    src = "../../monitoring/templates/x.j2"
    tasks = [
        {"name": "outer", "block": [{"template": {"src": src}}], "rescue": [{"block": [{"template": {"src": src}}]}]},
        {"always": [{"ansible.builtin.template": {"src": src}}]},
    ]
    assert [_template_src(t) for t in _walk_tasks(tasks) if _template_src(t)] == [src, src, src]
