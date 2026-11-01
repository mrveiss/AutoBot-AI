# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20517: rendering the backend's .env leaves no timestamped copy of its secrets beside it."""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_ROLE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "backend" / "tasks" / "main.yml"


def _walk(tasks: list) -> list[dict]:
    found = []
    for task in tasks:
        found.append(task)
        found += _walk(task.get("block") or [])
    return found


def _env_renders(tasks: list[dict]) -> list[dict]:
    templates = (task.get("ansible.builtin.template") for task in tasks)
    return [t for t in templates if t and str(t.get("dest", "")).endswith("/.env")]


def test_the_env_render_keeps_no_backup() -> None:
    renders = _env_renders(_walk(yaml.safe_load(_ROLE.read_text(encoding="utf-8"))))
    assert renders, "no .env render found; this test reads nothing"
    assert [r["dest"] for r in renders if r.get("backup")] == []


def test_contrast_a_backup_is_seen() -> None:
    task = {"ansible.builtin.template": {"dest": "/x/.env", "backup": True}}
    assert _env_renders(_walk([{"block": [task]}]))[0]["backup"] is True
