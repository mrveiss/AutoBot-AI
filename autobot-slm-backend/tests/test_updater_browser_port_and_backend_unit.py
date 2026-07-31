# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""PLAY 2 must wait on the right port and deliver the backend unit (#12912, #12777).

Two defects that together kept the builtin updater from ever succeeding:

**#12912** — `[PLAY 2] Browser | Wait for service to be ready` waited on port
3000. Nothing serves 3000: `autobot-playwright` binds `PLAYWRIGHT_PORT` (9001,
``roles/browser/defaults/main.yml``), and on a live host 3000 is Grafana bound to
loopback only. The wait timed out after 61 s and failed PLAY 2 on every run — the
terminal blocker. It also swallowed other components' notify handlers, which is
how the TTS worker kept serving stale code after its files had been delivered.

**#12777** — the backend systemd unit is role-owned and this play never rendered
it, so the faulthandler fix was merged, closed, and absent from every host. The
template had ``Environment="PYTHONFAULTHANDLER=1"``; ``systemctl cat
autobot-backend`` did not. It exists to make a SIGABRT crash loop diagnosable, so
its absence defeated the entire point of the issue.

Both are pinned here because both were invisible to the existing suite: the
playbook parses fine either way, and only a live run exposed them.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_BROWSER_DEFAULTS = _ANSIBLE / "roles" / "browser" / "defaults" / "main.yml"
_UNIT_ONLY = _ANSIBLE / "roles" / "backend" / "tasks" / "unit_only.yml"
_UNIT_TEMPLATE = _ANSIBLE / "roles" / "backend" / "templates" / "autobot-backend.service.j2"


def _iter_mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mappings(item)


def _browser_wait_task() -> dict:
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    for task in _iter_mappings(playbook):
        if "Browser | Wait for service" in str(task.get("name", "")):
            return task
    raise AssertionError("browser wait task not found")


def test_browser_wait_targets_the_port_the_worker_binds() -> None:
    """Waiting on 3000 is why PLAY 2 failed every run (#12912)."""
    port = str(_browser_wait_task().get("wait_for", {}).get("port", ""))

    assert "3000" not in port, (
        "the browser wait still targets 3000 — nothing serves it; on a live host "
        "that is Grafana on loopback, and the wait fails PLAY 2 every run"
    )
    assert "playwright_port" in port, (
        "the wait should follow playwright_port rather than hardcode a number"
    )
    assert "9001" in port, "keep a literal fallback: role defaults are not in scope here"


def test_browser_wait_fallback_matches_the_role_default() -> None:
    """The inline fallback must not drift from roles/browser/defaults."""
    defaults = yaml.safe_load(_BROWSER_DEFAULTS.read_text(encoding="utf-8"))
    declared = str(defaults["playwright_port"])

    assert declared in str(_browser_wait_task()["wait_for"]["port"]), (
        f"role default playwright_port={declared} but the playbook falls back to "
        "a different value — they must agree"
    )


def test_backend_unit_is_rendered_before_the_restart() -> None:
    """Rendering after the restart would start the OLD unit (#12777)."""
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))

    for play in playbook:
        tasks = play.get("tasks") or []
        render_idx = restart_idx = None
        for i, task in enumerate(tasks):
            inc = task.get("ansible.builtin.include_role") or task.get("include_role")
            if isinstance(inc, dict) and inc.get("name") == "backend":
                if inc.get("tasks_from") == "unit_only":
                    render_idx = i
            svc = task.get("systemd") or task.get("ansible.builtin.systemd") or {}
            if (
                isinstance(svc, dict)
                and svc.get("name") == "autobot-backend"
                and svc.get("state") == "restarted"
                and restart_idx is None
            ):
                restart_idx = i
        if render_idx is None and restart_idx is None:
            continue
        assert render_idx is not None, (
            "PLAY 2 never renders the backend unit — role-owned unit changes "
            "(e.g. #12777's faulthandler) cannot reach a host"
        )
        if restart_idx is not None:
            assert render_idx < restart_idx, (
                "the unit must be rendered BEFORE the restart, else the restart "
                "starts the old unit and the change only applies a run later"
            )
        return

    raise AssertionError("neither a backend unit render nor a restart was found")


def test_unit_only_renders_the_template_and_does_not_restart() -> None:
    """It must reload systemd, and leave restarting to the play's own task."""
    tasks = yaml.safe_load(_UNIT_ONLY.read_text(encoding="utf-8"))
    blob = str(tasks)

    assert "autobot-backend.service.j2" in blob, "the unit template must be rendered"
    assert "daemon_reload" in blob, "systemd must be reloaded after a unit change"
    assert "restarted" not in blob, (
        "unit_only must not restart — the play already restarts the backend, and "
        "a second restart would bounce it twice per update"
    )


def test_faulthandler_is_actually_in_the_unit_template() -> None:
    """Delivery is pointless if the artifact lacks what #12777 shipped."""
    assert "PYTHONFAULTHANDLER" in _UNIT_TEMPLATE.read_text(encoding="utf-8"), (
        "the unit template lost the faulthandler setting — rendering it would "
        "deliver a unit that still leaves a SIGABRT undiagnosable"
    )


def test_playbook_passes_ansible_syntax_check() -> None:
    """Only ansible's parser catches semantically invalid task keywords."""
    ansible = shutil.which("ansible-playbook")
    if ansible is None:
        pytest.skip("ansible-playbook not installed")

    result = subprocess.run(
        [ansible, "--syntax-check", "-i", "localhost,", str(_PLAYBOOK)],
        capture_output=True,
        text=True,
        cwd=_ANSIBLE,
        timeout=180,
    )

    assert result.returncode == 0, f"ansible rejected the playbook:\n{result.stderr[-1200:]}"
