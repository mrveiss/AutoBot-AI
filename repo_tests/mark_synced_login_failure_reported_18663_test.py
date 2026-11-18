# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The mark-synced tasks survive a login result that has no ``status`` (#18663).

What is known: on a failed install run the login task reported ok while its registered result
had no ``status`` key, and a bare ``_slm_login.status`` then raised an opaque conditional error.
The cause is NOT established (candidates: privilege escalation, the discovered interpreter, a
request error that returns no status). Every read must tolerate the missing key, the
localhost-delegated tasks must not escalate, and the playbook must name the cause on the next
failure by reporting the non-secret shape of the result.
"""

from __future__ import annotations

import re

import yaml
from repo_tests._paths import repo_root

_PLAYBOOK = "autobot-slm-backend/ansible/playbooks/provision-fleet-roles.yml"
_MARK = "Mark-synced | "


def _mark_synced_tasks(text: str) -> list[dict]:
    plays = yaml.safe_load(text)
    play = next(p for p in plays if p.get("name", "").startswith("Provision Phase 6.5"))
    return [t for t in play["tasks"] if t["name"].startswith(_MARK)]


def _module_args(task: dict, module: str) -> dict:
    """The task's module arguments, whether written short or as ``ansible.builtin.<module>``."""
    return task.get(module) or task["ansible.builtin." + module]


def _bare_status_reads(text: str) -> list[str]:
    """Reads of ``_slm_login.status`` that are not piped through ``default``."""
    return [m.group(0) for m in re.finditer(r"_slm_login\.status(?!\s*\|\s*default)", text)]


def _text() -> str:
    return (repo_root() / _PLAYBOOK).read_text(encoding="utf-8")


def test_every_login_status_read_tolerates_a_missing_status() -> None:
    assert not _bare_status_reads(_text())


def test_control_a_bare_status_read_is_detected() -> None:
    bare = _text().replace("(_slm_login.status | default(0)) != 200", "_slm_login.status != 200", 1)
    assert bare != _text(), "control did not change the playbook"
    assert _bare_status_reads(bare)


def test_login_and_post_do_not_escalate_on_the_install_inventory() -> None:
    by_name = {t["name"].split("{{")[0]: t for t in _mark_synced_tasks(_text())}
    for key in (_MARK + "Login to SLM API", _MARK + "POST to /api/code-sync/nodes/"):
        assert by_name[key].get("become") is False, key


def test_a_failed_login_is_reported_with_its_message() -> None:
    tasks = {t["name"]: t for t in _mark_synced_tasks(_text())}
    warn = tasks[_MARK + "Warn if login failed (skip mark-synced gracefully)"]
    assert "_slm_login.msg" in _module_args(warn, "debug")["msg"]


def test_a_failed_login_reports_the_result_shape_and_never_its_secrets() -> None:
    tasks = {t["name"]: t for t in _mark_synced_tasks(_text())}
    shape = next(t for n, t in tasks.items() if "shape of a login result" in n)
    text = _module_args(shape, "set_fact")["_slm_login_shape"]
    for field in ("keys() | list | sort", "_slm_login.msg", "_slm_login.module_stderr"):
        assert field in text, field
    fail = tasks[_MARK + "Fail the strict (install) run when the node was not stamped (#18663)"]
    assert "_slm_login_shape" in _module_args(fail, "fail")["msg"]
    assert not re.search(r"_slm_login\.(json|content|headers|cookies)\b", text)


def test_no_task_in_the_phase_prints_the_login_response_body() -> None:
    printing = [
        t["name"]
        for t in _mark_synced_tasks(_text())
        if any(m in t for m in ("debug", "ansible.builtin.debug", "ansible.builtin.fail"))
        and re.search(r"_slm_login\.(json|content)\b", yaml.safe_dump(t))
    ]
    assert not printing
