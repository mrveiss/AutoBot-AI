# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The builtin updater must refresh the deployed TTS worker (#12886).

The TTS worker had no update path at all. It is excluded from per-component
drift resolve (its deployed artifact is a rendered template, not a 1:1 sync of a
repo directory) and ``update-all-nodes.yml`` never mentioned it. So every backend
update advanced the caller while the worker stayed behind, and
``/tts/synthesize/stream`` — which ``services/tts_client.py`` calls — 404'd on a
host whose ``code_source`` was at origin tip.

That is the #12959 shape: the route existed in the role's template and had no
route to the host. These tests pin the wiring that closes it, and the property
that makes the wiring safe — that the updater runs the *code* tasks only, never
the provisioning half (service account, venv, torch/pocket-tts installs, gated
HuggingFace model pre-download), which is slow, needs network, and must not
re-run on an already-installed box.

The companion guard ``test_update_all_applies_roles_12959.py`` deliberately still
xfails after this: ``tasks_from`` is partial application, and a change to the
role's provisioning half would still not land. This closes the code half only.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_ROLE = _ANSIBLE / "roles" / "tts-worker"
_CODE_ONLY = _ROLE / "tasks" / "code_only.yml"
_MAIN = _ROLE / "tasks" / "main.yml"

#: Provisioning task substrings that must never run on an update path.
_PROVISIONING_MARKERS = ("venv", "pip", "pre-download", "service account", "system group")


def _iter_mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mappings(item)


def _includes_of(role: str) -> list[dict]:
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))
    found = []
    for task in _iter_mappings(playbook):
        inc = task.get("ansible.builtin.include_role") or task.get("include_role")
        if isinstance(inc, dict) and inc.get("name") == role:
            found.append(inc)
    return found


def test_updater_applies_the_tts_worker_role() -> None:
    """Without this the worker is never touched by the builtin updater at all."""
    includes = _includes_of("tts-worker")

    assert includes, (
        "update-all-nodes.yml does not apply the tts-worker role — "
        "the worker would silently rot behind the backend again (#12886)"
    )
    assert any(inc.get("tasks_from") == "code_only" for inc in includes), (
        "tts-worker must be applied via tasks_from=code_only; applying the full "
        "role would re-run provisioning on every update"
    )


def test_code_only_carries_the_service_files_and_no_provisioning() -> None:
    """The update path refreshes code, and must not re-provision the box."""
    tasks = yaml.safe_load(_CODE_ONLY.read_text(encoding="utf-8"))
    names = [t.get("name", "") for t in tasks]

    assert any("tts-worker.py" in n for n in names), "the worker itself must be refreshed"
    assert any("systemd service" in n for n in names), "the unit must be refreshed"

    lowered = " ".join(names).lower()
    for marker in _PROVISIONING_MARKERS:
        assert marker not in lowered, f"provisioning task leaked into the update path: {marker}"


def test_main_includes_code_only_rather_than_duplicating_it() -> None:
    """One definition of 'deploy the TTS service files', used by both paths.

    Copying the tasks into the playbook is exactly the inline-vs-role
    duplication that made this component undeliverable (#12959).
    """
    main = yaml.safe_load(_MAIN.read_text(encoding="utf-8"))

    included = [t.get("ansible.builtin.include_tasks") or t.get("include_tasks") for t in _iter_mappings(main)]
    assert "code_only.yml" in [
        i for i in included if isinstance(i, str)
    ], "roles/tts-worker/tasks/main.yml must include code_only.yml, not repeat its tasks"

    main_text = _MAIN.read_text(encoding="utf-8")
    assert (
        "tts-worker.py.j2" not in main_text
    ), "main.yml still renders tts-worker.py itself — that is a second definition"


def test_streaming_route_is_actually_in_the_template() -> None:
    """Delivery is pointless if the artifact lacks the route that 404'd."""
    template = (_ROLE / "templates" / "tts-worker.py.j2").read_text(encoding="utf-8")

    assert "/tts/synthesize/stream" in template, (
        "the route the backend calls is missing from the template — "
        "wiring the updater would deliver a worker that still 404s"
    )


def test_tts_include_escalates_privilege() -> None:
    """The include must escalate, via ``apply`` (#12886).

    This play sets no play-level ``become`` — unlike deploy-full.yml, which the
    role is normally applied under — and /opt/autobot/autobot-tts-worker is owned
    by the autobot-tts service account, not the user ansible connects as. Without
    escalation the first task dies "Destination ... not writable".

    It must be ``apply: {become: true}``, NOT a bare ``become:`` task keyword:
    ``become`` is not valid on include_role, and ansible rejects the ENTIRE
    playbook with "'become' is not a valid attribute for a IncludeRole" — which
    breaks every self-update, not just this task. Both mistakes were made on a
    live host before this test existed.
    """
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))

    for task in _iter_mappings(playbook):
        inc = task.get("ansible.builtin.include_role") or task.get("include_role")
        if isinstance(inc, dict) and inc.get("name") == "tts-worker":
            assert task.get("become") is None, (
                "bare `become:` on include_role makes ansible reject the whole " "playbook — use apply: {become: true}"
            )
            assert (inc.get("apply") or {}).get("become") is True, (
                "the tts-worker include must escalate via apply: {become: true} — "
                "the deployed tree is owned by a different service account"
            )
            return

    raise AssertionError("no tts-worker include_role task found")


def test_playbook_passes_ansible_syntax_check() -> None:
    """Validate with ansible itself, not just a YAML parse (#12886).

    A YAML-valid playbook can still be semantically invalid — a bare `become:`
    on include_role parses fine and then breaks every self-update at run time.
    Only ansible's own parser catches that class, so gate on it here.
    """
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


def test_tts_service_is_restarted_explicitly() -> None:
    """The worker must be restarted by a task, not a notify handler (#12886).

    Two failures made handler-driven restart unusable here, both seen on a live
    host. Handlers flush at END of play, and PLAY 2 dies at the browser tasks
    (#12912), so the queued restart was discarded and the worker served 4-day-old
    code. Then, once the file was already current, the template reported `ok` and
    never notified at all — leaving a host that had the file but not the restart
    permanently stale, with nothing left to trigger it.

    Delivering a file without restarting the process is not delivery.
    """
    playbook = yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))

    for play in playbook:
        tasks = play.get("tasks") or []
        tts_idx = restart_idx = None
        for i, task in enumerate(tasks):
            inc = task.get("ansible.builtin.include_role") or task.get("include_role")
            if isinstance(inc, dict) and inc.get("name") == "tts-worker":
                tts_idx = i
            svc = task.get("systemd") or task.get("ansible.builtin.systemd") or {}
            if (
                isinstance(svc, dict)
                and svc.get("name") == "autobot-tts-worker"
                and svc.get("state") == "restarted"
                and tts_idx is not None
                and restart_idx is None
            ):
                restart_idx = i
        if tts_idx is None:
            continue
        assert restart_idx is not None, (
            "no explicit autobot-tts-worker restart after the include — a notify "
            "handler is lost to end-of-play failures and never fires when the "
            "file is already current"
        )
        assert restart_idx > tts_idx, "the restart must come AFTER the include"
        return

    raise AssertionError("no play contained the tts-worker include")
