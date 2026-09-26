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

The checks live in one function, `_violations`, and are exercised on both
sides: the real task must yield none, and each broken fixture in `_BROKEN` --
a negated or foreign `until`, a budget below the floor, a swallowed failure --
must yield at least one. The negated `until` (`not (x is succeeded)`) is the
case a substring match let through: it contains every expected word while
inverting when the retry stops.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_HELPER = _ANSIBLE / "roles" / "_shared" / "tasks" / "add_apt_repository_idempotent.yml"
_MODULES = ("ansible.builtin.apt_repository", "apt_repository")
_BUDGET_VARS = ("apt_repo_retries", "apt_repo_retry_delay")
#: A YAML (`name:`, incl. a `- name:` list item) or INI inventory (`name=`) assignment of a budget var.
_ASSIGNMENT = re.compile(r"^\s*(?:-\s*)?(?:" + "|".join(_BUDGET_VARS) + r")\s*[:=]", re.MULTILINE)


def _add_tasks() -> list[dict]:
    """Every apt_repository task in the shared helper, loaded from YAML."""
    assert _HELPER.is_file(), (
        f"{_HELPER.relative_to(repo_root())} is missing. Seven roles include it to add apt repos; "
        "if it moved, move this guard with it rather than deleting the guard."
    )
    loaded = yaml.safe_load(_HELPER.read_text(encoding="utf-8"))
    assert isinstance(loaded, list) and loaded, "expected a non-empty Ansible task list"
    return [t for t in loaded if isinstance(t, dict) and any(m in t for m in _MODULES)]


def _budget(value) -> int | None:
    """The effective integer of a literal or a `{{ var | default(N) }}` template, else None."""
    if isinstance(value, int):
        return value
    match = re.search(r"default\(\s*(\d+)\s*\)", str(value))
    return int(match.group(1)) if match else None


def _violations(task: dict) -> list[str]:
    """Why ``task`` would not retry a transient failure while still failing a persistent one."""
    registered = task.get("register")
    if not registered:
        return ["registers no result, so `until` has nothing to test"]
    problems = []
    until = " ".join(str(task.get("until", "")).split())
    if until != f"{registered} is succeeded":
        problems.append(f"`until: {until!r}` is not exactly `{registered} is succeeded`")
    if (_budget(task.get("retries")) or 0) < 2:
        problems.append(f"`retries: {task.get('retries')!r}` is below 2, which is no retry at all")
    if (_budget(task.get("delay")) or 0) < 1:
        problems.append(f"`delay: {task.get('delay')!r}` hammers a keyserver that just failed")
    if "failed_when" in task:
        problems.append(
            f"`failed_when: {task['failed_when']!r}` is not allowed on this task -- the retry budget is "
            "the only failure policy here"
        )
    if task.get("ignore_errors"):
        problems.append("`ignore_errors` lets the play continue without the repo")
    return problems


_GOOD = {
    "ansible.builtin.apt_repository": {"repo": "ppa:example/ppa"},
    "register": "_r",
    "until": "_r is succeeded",
    "retries": "{{ apt_repo_retries | default(5) }}",
    "delay": 10,
}
_BROKEN = {
    "no-until": {k: v for k, v in _GOOD.items() if k != "until"},
    "negated-until": {**_GOOD, "until": "not (_r is succeeded)"},
    "foreign-until": {**_GOOD, "until": "_apt_repo_present is succeeded"},
    "no-register": {k: v for k, v in _GOOD.items() if k != "register"},
    "one-retry": {**_GOOD, "retries": "{{ apt_repo_retries | default(1) }}"},
    "untemplated-retries": {**_GOOD, "retries": "{{ apt_repo_retries }}"},
    "no-delay": {**_GOOD, "delay": 0},
    "failed-when-false": {**_GOOD, "failed_when": False},
    "ignore-errors": {**_GOOD, "ignore_errors": True},
}


def test_there_is_exactly_one_repo_add_task() -> None:
    """Pin what the other tests look at, so a second, unretried add cannot slip in beside it."""
    tasks = _add_tasks()
    assert len(tasks) == 1, (
        f"expected one apt_repository task in {_HELPER.name}, found {len(tasks)}: "
        f"{[t.get('name') for t in tasks]}. Every one of them needs the #17230 retry."
    )


def test_the_repo_add_retries_and_still_fails_loudly() -> None:
    """The real task retries a transient failure and stops the play once the budget is spent (#17230)."""
    (task,) = _add_tasks()
    problems = _violations(task)
    assert not problems, f"{_HELPER.name}'s repo add is not safely retried (#17230):\n  " + "\n  ".join(problems)


def test_the_checker_accepts_a_correct_task() -> None:
    """Contrast half: a correctly retried task must pass, or every failure above is noise."""
    assert _violations(_GOOD) == []


@pytest.mark.parametrize("task", _BROKEN.values(), ids=_BROKEN.keys())
def test_the_checker_rejects_a_broken_task(task: dict) -> None:
    """Contrast half: each way of breaking the retry must be caught, including a negated `until`."""
    assert _violations(task), f"the checker passed a task it must reject: {task}"


def _overrides(text: str) -> list[str]:
    """Lines of ``text`` that assign a retry-budget variable."""
    return [m.group(0).strip() for m in _ASSIGNMENT.finditer(text)]


def test_no_file_overrides_the_retry_budget() -> None:
    """The budget checks above read ``default(N)``, so they hold only while nothing overrides it.

    Setting ``apt_repo_retries: 1`` in a role, ``group_vars`` or an inventory would switch the retry
    off while ``_budget`` still reads 5. Rather than evaluate Ansible, pin that the default is the
    effective value: the day an override is needed, this fails and asks for the check to follow it.
    Out of reach by construction: ``-e`` on a command line and inventories outside this tree.
    """
    hits = [
        f"{path.relative_to(repo_root())}: {line}"
        for path in sorted(_ANSIBLE.rglob("*"))
        if path.is_file() and path.suffix in {".yml", ".yaml", ".ini", ".cfg", ""}
        for line in _overrides(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not hits, (
        "these override the #17230 retry budget, so the guard's `default(N)` reading is no longer the "
        "effective value -- extend the budget check to the override before keeping it:\n  " + "\n  ".join(hits)
    )


@pytest.mark.parametrize(
    "text, expected",
    [
        ("apt_repo_retries: 1\n", 1),
        ("vars:\n  apt_repo_retry_delay: 0\n", 1),
        ("- apt_repo_retries: 2\n", 1),
        ("[all:vars]\napt_repo_retries=1\n", 1),
        ("#   apt_repo_retries  (int, opt.) Retry budget (default 5).\n", 0),
        ('  retries: "{{ apt_repo_retries | default(5) }}"\n', 0),
    ],
    ids=["yaml", "nested-yaml", "list-item", "ini-inventory", "comment", "the-template-reading-it"],
)
def test_the_override_detector_matches_assignments_only(text: str, expected: int) -> None:
    """Contrast pair: every assignment form trips it; the helper's own comment and template do not."""
    assert len(_overrides(text)) == expected, _overrides(text)
