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
