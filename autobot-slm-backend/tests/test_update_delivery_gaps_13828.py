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
_ROLES = _ANSIBLE / "roles"
_UNIT_ONLY = _ROLES / "backend" / "tasks" / "unit_only.yml"
_MAIN = _ROLES / "backend" / "tasks" / "main.yml"
_ENROLL = _ANSIBLE / "playbooks" / "enroll-node.yml"
_SERVICE_PLAYBOOKS = ("slm-service-control.yml", "slm-service-logs.yml")


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


def _systemd_units(path: Path) -> set[str]:
    """Unit basenames a task file writes under /etc/systemd/system.

    Reads both the direct `dest:` form and a loop over unit names, so the two
    files can be compared however each happens to be written.
    """
    units: set[str] = set()
    for task in _walk_tasks(_load(path)):
        for mod in ("ansible.builtin.template", "template", "ansible.builtin.copy", "copy"):
            spec = task.get(mod)
            dest = str(spec.get("dest", "")) if isinstance(spec, dict) else ""
            if "/etc/systemd/system/" in dest and dest.endswith(".service"):
                units.add(Path(dest).name)
            if "/etc/systemd/system/" in dest and "{{ item }}" in dest:
                units.update(str(i) for i in (task.get("loop") or []))
    return units


def test_unit_only_renders_every_unit_main_installs() -> None:
    """The set rendered by unit_only.yml must equal the set main.yml installs.

    Compared against `main.yml` rather than against the templates on disk: a
    template can exist without the role installing it (`autobot-mcp-bridge@.service`
    is exactly that, #14827), so the templates are the wrong denominator. What
    matters for the update path is that every unit the role *installs* can also be
    refreshed without a full role run.
    """
    installed = _systemd_units(_MAIN)
    rendered = _systemd_units(_UNIT_ONLY)
    assert installed, "main.yml installs no units — this guard would pass vacuously"

    missing = installed - rendered
    assert not missing, (
        f"unit_only.yml does not render {sorted(missing)} — changes to those units "
        "cannot reach a host through the updater, which is the whole point of the include"
    )

    extra = rendered - installed
    assert not extra, (
        f"unit_only.yml renders {sorted(extra)} that main.yml does not install — "
        "the two have diverged in the other direction"
    )


def test_backend_is_still_the_only_role_with_a_unit_only_include() -> None:
    """The cross-role audit, pinned rather than recorded once and forgotten.

    #13828 asked whether other roles share the main/unit_only asymmetry. At the
    time only `backend` had a `unit_only.yml`, so there was nothing else to
    diverge. If another role gains one, it needs the same equality check and this
    fails to say so.
    """
    roles = sorted(p.parent.parent.name for p in _ROLES.glob("*/tasks/unit_only.yml"))
    assert roles == [
        "backend"
    ], f"roles with a unit_only.yml are now {roles} — extend the equality check above to each of them"


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


def test_the_enrolled_hook_is_the_agent_notifier() -> None:
    """A node needs the notifier, whichever file ends up providing it.

    Two files currently share this basename: the repo-root one heals stash-pop
    conflict markers (#2416), the infrastructure one notifies the SLM agent of
    commits (#741). #14176 asks for them to be consolidated into one with both
    behaviours folded in, so this deliberately asserts the *behaviour* the
    enrolled hook must have rather than which of the two files it is — otherwise
    this guard would fail the moment that consolidation happens.
    """
    src = None
    for task in _walk_tasks(_load(_ENROLL)):
        if "post-commit hook" in str(task.get("name", "")).lower():
            src = str((task.get("copy") or task.get("ansible.builtin.copy") or {}).get("src", ""))
    assert src, "no post-commit hook copy task found — this guard would pass vacuously"

    resolved = (_ANSIBLE / "playbooks" / src.replace("{{ playbook_dir }}/", "")).resolve()
    assert resolved.is_file(), f"hook source does not exist: {resolved}"
    body = resolved.read_text(encoding="utf-8").lower()
    assert "agent" in body, (
        "the hook a node is given no longer notifies the SLM agent — enrolment would deploy "
        "a hook that does not do the job enrolment needs"
    )
