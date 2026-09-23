# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every `roles/_shared/tasks/*.yml` template of `code_source_dir` must carry
its own `| default(` (#16750).

`_shared/tasks/` files run from more than one role's context (backend,
frontend, npu-worker, slm_manager, ...), and not every caller sets
`code_source_dir` -- the frontend role never does. #16351 added
`_shared/tasks/sync_deletions.yml`'s "resolve the commit being deployed" task
with a bare `{{ code_source_dir }}`, so in the frontend role's context it
templated undefined, the task failed, and the block's rescue silently skipped
the whole deletion pass with a warning -- caught only on a real `update-all`
run on 2026-09-14, never by CI (CI does not execute Ansible).

A `_shared/tasks/*.yml` file may reference `code_source_dir` bare in a
`set_fact:` that resolves it to a LOCAL fallback variable once (the module's
own override-first, SSOT-derived default, matching how its callers already
compute `sync_deletions_source_dir`), and every other site must reference
that local variable, not the bare name again. The check below does not care
which shape a file picks -- it only requires that every `{{ ... }}`
expression containing `code_source_dir` also contains `default(` in the same
expression.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_REPO_ROOT = repo_root()
_ANSIBLE = _REPO_ROOT / "autobot-slm-backend" / "ansible"
_SHARED_TASKS_DIR = _ANSIBLE / "roles" / "_shared" / "tasks"

#: Non-greedy DOTALL: a Jinja expression a `>-` block scalar folds onto more
#: than one physical line must still be read whole, not truncated at the
#: first newline.
_JINJA_EXPR_RE = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_BARE_CODE_SOURCE_DIR_RE = re.compile(r"\bcode_source_dir\b")

#: Floor on FILES SCANNED, never on offenders found -- an offenders floor is
#: satisfied by finding nothing, indistinguishable from a directory that
#: stopped resolving. 7 files measured 2026-09-14.
_MIN_SHARED_TASK_FILES = 5


def _shared_task_files() -> list[Path]:
    assert _SHARED_TASKS_DIR.is_dir(), f"{_SHARED_TASKS_DIR} not found -- _shared/tasks/ moved or was renamed"
    return sorted(_SHARED_TASKS_DIR.glob("*.yml"))


def _bare_code_source_dir_expressions(text: str) -> list[str]:
    """Jinja expressions in *text* that reference code_source_dir with no
    `default(` anywhere in the SAME expression."""
    offenders = []
    for expr in _JINJA_EXPR_RE.findall(text):
        if _BARE_CODE_SOURCE_DIR_RE.search(expr) and "default(" not in expr:
            offenders.append(expr.strip())
    return offenders


def test_the_sweep_reaches_shared_tasks_files() -> None:
    """Reach before findings -- an empty walk must fail, not pass silently."""
    files = _shared_task_files()
    assert len(files) >= _MIN_SHARED_TASK_FILES, (
        f"found only {len(files)} files under {_SHARED_TASKS_DIR.relative_to(_REPO_ROOT)} "
        f"(floor {_MIN_SHARED_TASK_FILES}) -- the walk has stopped reading"
    )


def test_no_shared_task_file_templates_code_source_dir_without_a_default() -> None:
    """#16750: a bare {{ code_source_dir }} is undefined in any caller that
    never sets it (e.g. the frontend role) -- every reference must fall back."""
    offenders: dict[str, list[str]] = {}
    for path in _shared_task_files():
        exprs = _bare_code_source_dir_expressions(path.read_text(encoding="utf-8"))
        if exprs:
            offenders[str(path.relative_to(_REPO_ROOT))] = exprs

    assert not offenders, (
        "these _shared/tasks/ files template code_source_dir with no | default(...) in the same "
        "Jinja expression -- it is undefined in any caller that never sets it (#16351/#16750):\n  "
        + "\n  ".join(f"{path}: {exprs}" for path, exprs in offenders.items())
    )


# --------------------------------------------------------------------------
# Fixture: prove the detector actually catches the old sync_deletions shape,
# rather than trusting the live sweep alone to exercise both branches.
# --------------------------------------------------------------------------

_OLD_SYNC_DELETIONS_SHAPE = """\
- name: "Deletions: resolve the commit being deployed"
  ansible.builtin.command:
    cmd: git -c safe.directory={{ code_source_dir }} -C {{ code_source_dir }} rev-parse HEAD
  delegate_to: localhost
"""

_FIXED_SYNC_DELETIONS_SHAPE = """\
- name: "Deletions: resolve code_source_dir"
  ansible.builtin.set_fact:
    _sd_code_source_dir: "{{ code_source_dir | default(autobot.base_dir ~ '/code_source') }}"

- name: "Deletions: resolve the commit being deployed"
  ansible.builtin.command:
    cmd: git -c safe.directory={{ _sd_code_source_dir }} -C {{ _sd_code_source_dir }} rev-parse HEAD
  delegate_to: localhost
"""


def test_the_old_sync_deletions_shape_is_detected_as_broken() -> None:
    """#16750: a bare code_source_dir reference must fail the check --
    proving the detector would have caught the real regression."""
    offenders = _bare_code_source_dir_expressions(_OLD_SYNC_DELETIONS_SHAPE)
    assert offenders, "the fixture must be detected as broken -- the detector is not exercising this branch"


def test_the_fixed_sync_deletions_shape_is_detected_as_defaulted() -> None:
    """The SAME fixture, with the local-fallback shape applied, must pass --
    proving the detector is not just always-false."""
    offenders = _bare_code_source_dir_expressions(_FIXED_SYNC_DELETIONS_SHAPE)
    assert not offenders, f"the fixed fixture must have no offenders, found: {offenders}"


def test_the_live_sync_deletions_file_is_covered_by_the_sweep() -> None:
    """The exact file the regression shipped in stays inside the population
    this guard scans -- a future rename or move must not silently drop it."""
    files = {str(p.relative_to(_REPO_ROOT)) for p in _shared_task_files()}
    assert "autobot-slm-backend/ansible/roles/_shared/tasks/sync_deletions.yml" in files
