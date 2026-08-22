# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Three ways a change could not reach a host, or a no-op reported success.

#13828 — `roles/backend/tasks/unit_only.yml` rendered only autobot-backend.service.
         The include exists so unit changes reach hosts WITHOUT a full role run
         (#12777), and the update path never does a full run — so celery unit
         changes could not reach a host at all.

#13786 — `slm-service-control.yml` / `slm-service-logs.yml` declared `hosts: target`.
         No inventory defines it. A play whose pattern matches nothing is skipped
         silently (ok=0, changed=0, exit 0), which for a service-control playbook
         reads as "the restart succeeded".

#14176 — enroll-node.yml copied the post-commit hook from a path that does not
         exist, and two different hooks share that basename: the repo-root one
         heals stash-pop conflict markers (#2416), the infrastructure one notifies
         the SLM agent of commits (#741). A node needs the second.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO / "autobot-slm-backend" / "ansible"
_UNIT_ONLY = _ANSIBLE / "roles" / "backend" / "tasks" / "unit_only.yml"
_TEMPLATES = _ANSIBLE / "roles" / "backend" / "templates"
_ENROLL = _ANSIBLE / "playbooks" / "enroll-node.yml"
_SERVICE_PLAYBOOKS = ("slm-service-control.yml", "slm-service-logs.yml")


#: #14827 — templated, monitored, and rendered by nothing. Excluded by NAME with
#: a pointer to the issue rather than by a pattern, so it cannot quietly absorb a
#: future unit that is merely forgotten. Delete this line when #14827 lands.
_NOT_YET_WIRED = {"autobot-mcp-bridge@.service"}


def _load(path: Path):
    assert path.is_file(), f"file under test is missing: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _walk_tasks(container):
    """Yield tasks from a play or block, including nested ones.

    `tasks` alone is not enough: enroll-node.yml nests the hook copy inside a
    block, and a guard reading only the top level reports "not found" — which
    looks exactly like the task having been removed.
    """
    if isinstance(container, list):
        for item in container:
            yield from _walk_tasks(item)
        return
    if not isinstance(container, dict):
        return
    yield container
    for key in ("tasks", "pre_tasks", "post_tasks", "block", "rescue", "always"):
        if container.get(key):
            yield from _walk_tasks(container[key])


def test_unit_only_renders_every_unit_the_role_owns() -> None:
    """Derived from the templates on disk, not from a hand-written list.

    A guard listing the same three names it checks would pass forever; this one
    fails when a fourth unit template is added and not wired in.
    """
    owned = {p.name[: -len(".j2")] for p in _TEMPLATES.glob("*.service.j2")} - _NOT_YET_WIRED
    assert owned, "no unit templates found — this guard would pass vacuously"
    assert len(owned) >= 3, f"expected at least the three managed units, got {sorted(owned)}"

    rendered: set[str] = set()
    for task in _load(_UNIT_ONLY):
        if not isinstance(task, dict):
            continue
        for item in task.get("loop") or []:
            rendered.add(str(item))
        dest = str((task.get("ansible.builtin.template") or {}).get("dest", ""))
        if dest:
            rendered.add(Path(dest).name)

    missing = owned - rendered
    assert not missing, (
        f"unit_only.yml does not render {sorted(missing)} — changes to those units "
        "cannot reach a host through the updater"
    )


def test_service_control_playbooks_fail_loudly_without_a_target() -> None:
    """A bare group name that matches nothing is skipped silently."""
    for name in _SERVICE_PLAYBOOKS:
        plays = _load(_ANSIBLE / "playbooks" / name)
        for play in plays:
            hosts = str(play.get("hosts", ""))
            assert "{{" in hosts, (
                f"{name} declares `hosts: {hosts}` as a bare name — a run that passes no "
                "target matches nothing and reports success"
            )


def test_enroll_node_hook_source_exists() -> None:
    """The copy pointed at a directory that has never existed."""
    src = None
    for task in _walk_tasks(_load(_ENROLL)):
        if "post-commit hook" in str(task.get("name", "")).lower():
            src = str((task.get("copy") or task.get("ansible.builtin.copy") or {}).get("src", ""))
    assert src, "no post-commit hook copy task found — this guard would pass vacuously"

    resolved = (_ANSIBLE / "playbooks" / src.replace("{{ playbook_dir }}/", "")).resolve()
    assert resolved.is_file(), f"hook source does not exist: {resolved}"


def test_the_node_hook_is_the_agent_notifier_not_the_developer_hook() -> None:
    """Two different files share this basename; a node needs the notifier."""
    node_hook = _REPO / "autobot-infrastructure" / "shared" / "scripts" / "hooks" / "slm-post-commit"
    dev_hook = _REPO / "scripts" / "hooks" / "slm-post-commit"
    assert node_hook.is_file() and dev_hook.is_file(), "expected both hooks to exist"
    assert node_hook.read_bytes() != dev_hook.read_bytes(), (
        "the two hooks are now identical — if they were deduplicated, this guard and "
        "the enroll-node src both need revisiting"
    )
    assert "agent" in node_hook.read_text(encoding="utf-8").lower(), "the node hook no longer looks like the notifier"
