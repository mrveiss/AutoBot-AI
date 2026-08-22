# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The update path must deliver before it consumes, and verify in a way that can fail.

Four defects that shared one property: the playbook parses fine either way, so
only a live run exposed them.

#14809 — the ai-stack role installed from `requirements-ai.txt` and refreshed
         that file *afterwards*, in the application-source loop. A bad
         requirements file was therefore self-perpetuating: the failing install
         aborted the play before the copy that would replace it. The node kept
         installing spacy long after #14279 removed it for lacking py3.14
         wheels, and the fix could not arrive.

#14701 — Play 3's "Check SLM health" carried `ignore_errors: true` and fed only
         the summary text, so a run whose SLM never came back still reported
         "Fleet Update Complete" and exited zero.

#14700 — the slm-admin-ui systemd tasks relied on the caller escalating, the
         same shape that broke in #14693.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_AI_STACK = _ANSIBLE / "roles" / "ai-stack" / "tasks" / "main.yml"
_SLM_MANAGER = _ANSIBLE / "roles" / "slm_manager" / "tasks" / "main.yml"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"


def _load(path: Path):
    assert path.is_file(), f"file under test is missing: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _index_of(tasks, needle: str) -> int:
    for i, t in enumerate(tasks):
        if isinstance(t, dict) and needle in str(t.get("name", "")):
            return i
    raise AssertionError(f"no task matching {needle!r} — this guard would pass vacuously")


def test_ai_stack_delivers_requirements_before_installing_from_them() -> None:
    """The regression: delivery must not be gated behind the step it unbreaks."""
    tasks = _load(_AI_STACK)
    deliver = _index_of(tasks, "Deploy requirements-ai.txt")
    filtered = _index_of(tasks, "Create filtered AI-stack requirements")
    install = _index_of(tasks, "Install AI Python packages from requirements")
    assert deliver < filtered < install, (
        "requirements-ai.txt is delivered after it is filtered/installed — a bad "
        f"requirements file becomes unfixable (deliver={deliver}, filter={filtered}, install={install})"
    )


def test_requirements_are_not_delivered_twice() -> None:
    """Copying it again later would reintroduce the ordering ambiguity."""
    raw = _AI_STACK.read_text(encoding="utf-8")
    assert (
        raw.count("ai-stack/requirements-ai.txt") == 1
    ), "requirements-ai.txt is referenced more than once — the later copy is the one that used to be too late"


def test_play_three_health_check_can_fail_the_run() -> None:
    """A stage named Verify that cannot fail is worse than no stage."""
    plays = _load(_PLAYBOOK)
    for play in plays:
        for task in play.get("tasks") or []:
            if "Check SLM health" in str(task.get("name", "")):
                assert (
                    task.get("ignore_errors") is not True
                ), "Play 3's health check still ignores errors — a run can report complete with the SLM down"
                assert task.get("until"), "the health check does not retry, so it races the restart before it"
                return
    raise AssertionError("no 'Check SLM health' task found — this guard would pass vacuously")


def test_admin_ui_systemd_tasks_escalate() -> None:
    """Same shape as #14693: root-owned writes must not depend on the caller."""
    tasks = _load(_SLM_MANAGER)
    admin = [t for t in tasks if isinstance(t, dict) and "slm-admin-ui" in str(t.get("name", ""))]
    assert admin, "no slm-admin-ui tasks found — this guard would pass vacuously"
    missing = [t.get("name") for t in admin if t.get("become") is not True]
    assert not missing, f"these tasks write systemd state without escalating: {missing}"
