# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16970/#17096 review: the co-location `stat` task's SSOT default must
actually render, not merely avoid the literal hardcode.

The fallback for `frontend_dist_dir` was `default(base_dir + '/autobot-frontend/dist')`
-- but `base_dir` is not a top-level fact this play would ever see:
`ansible/inventory/group_vars/all.yml` nests it under `autobot:`
(`autobot.base_dir`). Jinja's `default()` evaluates its argument eagerly, so
every render where `frontend_dist_dir` is unset -- the normal case, since only
`roles/frontend`'s own defaults set it -- raised `UndefinedError` instead of
falling back. Caught in review before merge; asserted here so the next `s/./ /`
inside this expression fails a test rather than a live run.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest
import yaml
from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_PLAYBOOK = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "playbooks" / "provision-fleet-roles.yml"
_TASK_NAME = "SLM | Stat user frontend package.json for co-location detection"

#: The real group_vars/all.yml value, so a drift there is exercised too.
_GROUP_VARS = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "inventory" / "group_vars" / "all.yml"


def _jinja_env():
    jinja2 = pytest.importorskip("jinja2")
    env = jinja2.Environment()  # nosec B701  # repo-owned Ansible sources, never user input
    env.filters["dirname"] = lambda value: str(PurePosixPath(str(value)).parent)
    return env


def _find_task_path_expr() -> str:
    documents = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    for document in documents:
        for task in document.get("tasks", []) or []:
            if isinstance(task, dict) and task.get("name") == _TASK_NAME:
                return task["ansible.builtin.stat"]["path"]
    raise AssertionError(f"task {_TASK_NAME!r} moved or was renamed in {_PLAYBOOK}")


def _autobot_base_dir() -> str:
    group_vars = yaml.safe_load(_GROUP_VARS.read_text(encoding="utf-8"))
    return group_vars["autobot"]["base_dir"]


def test_the_task_and_its_expression_are_found():
    """A derivation that finds nothing would make the render check vacuous."""
    expr = _find_task_path_expr()
    assert "frontend_dist_dir" in expr and "default(" in expr, f"expression shape changed: {expr!r}"
    assert _autobot_base_dir(), "group_vars/all.yml no longer sets autobot.base_dir"


def test_renders_with_frontend_dist_dir_undefined():
    """The normal case (#17096 review finding 1): only roles/frontend's own
    defaults set frontend_dist_dir, so this bare `hosts: all` play never has
    it -- the fallback must render, not raise.
    """
    expr = _find_task_path_expr()  # already the full "{{ ... }}/package.json" string
    rendered = _jinja_env().from_string(expr).render(autobot={"base_dir": _autobot_base_dir()})
    assert rendered == f"{_autobot_base_dir()}/autobot-frontend/package.json"


def test_a_bare_base_dir_reference_would_have_raised():
    """Contrast mutation: proves the check catches the exact bug found in
    review -- `base_dir` (not nested under `autobot`) is undefined.
    """
    jinja2 = pytest.importorskip("jinja2")
    env = _jinja_env()
    with pytest.raises(jinja2.UndefinedError):
        env.from_string("{{ frontend_dist_dir | default(base_dir + '/x') | dirname }}").render()


def test_frontend_dist_dir_set_still_wins_over_the_default():
    """The fallback only ever applies when frontend_dist_dir is truly unset."""
    expr = _find_task_path_expr()
    rendered = (
        _jinja_env()
        .from_string(expr)
        .render(
            frontend_dist_dir="/opt/autobot/autobot-frontend/current",
            autobot={"base_dir": _autobot_base_dir()},
        )
    )
    assert rendered == "/opt/autobot/autobot-frontend/package.json"
