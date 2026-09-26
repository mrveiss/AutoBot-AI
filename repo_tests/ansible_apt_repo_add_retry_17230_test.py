# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared apt repository add retries a transient failure and still fails loudly (#17230).

`roles/_shared/tasks/add_apt_repository_idempotent.yml` ends in an
`ansible.builtin.apt_repository` task. For a `ppa:` spec that task fetches the
signing key from the keyserver at provisioning time; for a `deb https://` spec
it reaches the repository host. It declared no `retries`/`until`, so one
`gpg: keyserver receive failed: End of file` aborted the play in the
`python_interpreter` role -- while the cache refresh *after* it was already
hardened against the same PPA being unreachable.

The helper is included by every role that adds a repo (7 include sites in 7
roles), so the retry lands once here and this guard asserts it once. CI does
not execute Ansible, so the guard reads the task file, as the #16020 and
#17172 guards do.

Mutation checks: drop `until:` (or point it at another variable), set
`retries` to 0/1, or add `failed_when: false` / `ignore_errors: true` to the
task, and a test here goes red naming it.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_HELPER = _ANSIBLE / "roles" / "_shared" / "tasks" / "add_apt_repository_idempotent.yml"
_MODULES = ("ansible.builtin.apt_repository", "apt_repository")


def _add_tasks() -> list[dict]:
    assert _HELPER.is_file(), (
        f"{_HELPER.relative_to(repo_root())} is missing. Seven roles include it to add apt repos; "
        "if it moved, move this guard with it rather than deleting the guard."
    )
    loaded = yaml.safe_load(_HELPER.read_text(encoding="utf-8"))
    assert isinstance(loaded, list) and loaded, "expected a non-empty Ansible task list"
    return [t for t in loaded if isinstance(t, dict) and any(m in t for m in _MODULES)]


def _budget(value) -> int:
    """The effective integer of a literal or a `{{ var | default(N) }}` template."""
    if isinstance(value, int):
        return value
    match = re.search(r"default\(\s*(\d+)\s*\)", str(value))
    assert match, f"cannot read a default budget out of {value!r}; give it a `| default(N)`"
    return int(match.group(1))


def test_there_is_exactly_one_repo_add_task() -> None:
    """Pin what the other tests look at, so a second, unretried add cannot slip in beside it."""
    tasks = _add_tasks()
    assert len(tasks) == 1, (
        f"expected one apt_repository task in {_HELPER.name}, found {len(tasks)}: "
        f"{[t.get('name') for t in tasks]}. Every one of them needs the #17230 retry."
    )


def test_the_repo_add_retries_until_it_succeeds() -> None:
    (task,) = _add_tasks()
    registered = task.get("register")
    assert registered, "the repo add registers no result, so `until` has nothing to test (#17230)"
    until = str(task.get("until", ""))
    assert registered in until and "succeeded" in until, (
        f"`until: {until!r}` does not wait for `{registered} is succeeded`; without it Ansible does "
        "not retry a failed apt_repository and one keyserver hiccup aborts provisioning (#17230)"
    )
    assert _budget(task.get("retries")) >= 2, "a retry budget below 2 is no retry at all"
    assert _budget(task.get("delay")) >= 1, "retrying with no delay hammers a keyserver that just failed"


def test_an_exhausted_retry_budget_still_fails_the_play() -> None:
    """A repo that genuinely cannot be added must stop the deploy, not vanish into a later apt error."""
    (task,) = _add_tasks()
    assert "failed_when" not in task, f"failed_when: {task['failed_when']!r} would swallow a real failure"
    assert not task.get("ignore_errors"), "ignore_errors would let the play continue without the repo"
