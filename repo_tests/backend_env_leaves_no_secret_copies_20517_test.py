# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20517: rendering the backend's .env leaves no timestamped copy of its secrets beside it."""

from __future__ import annotations

import pytest
import yaml
from repo_tests._paths import repo_root

_TASKS = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "tasks"
#: Every task file in the role that renders the env file; env_only.yml is the one the updater runs.
_RENDERERS = ("main.yml", "env_only.yml")


def _walk(tasks: list) -> list[dict]:
    found = []
    for task in tasks:
        found.append(task)
        found += _walk(task.get("block") or [])
    return found


def _env_renders(tasks: list[dict]) -> list[dict]:
    templates = (task.get("ansible.builtin.template") for task in tasks)
    return [t for t in templates if t and str(t.get("src", "")) == "backend.env.j2"]


@pytest.mark.parametrize("name", _RENDERERS)
def test_the_env_render_keeps_no_backup(name: str) -> None:
    renders = _env_renders(_walk(yaml.safe_load((_TASKS / name).read_text(encoding="utf-8"))))
    assert renders, "no env render found; this test reads nothing"
    assert [r["dest"] for r in renders if r.get("backup")] == []


def test_the_list_of_renderers_is_complete() -> None:
    """A new task file rendering the env must join the list, so the check above reads it."""
    rendering = {p.name for p in _TASKS.glob("*.yml") if "src: backend.env.j2" in p.read_text(encoding="utf-8")}
    assert rendering == set(_RENDERERS)


def test_contrast_a_backup_is_seen() -> None:
    task = {"ansible.builtin.template": {"src": "backend.env.j2", "dest": "/x/.env", "backup": True}}
    assert _env_renders(_walk([{"block": [task]}]))[0]["backup"] is True
