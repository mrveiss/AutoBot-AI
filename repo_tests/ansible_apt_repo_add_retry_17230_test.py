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
a negated or foreign `until`, a budget that is not the documented variable and default, a swallowed failure --
must yield at least one. The negated `until` (`not (x is succeeded)`) is the
case a substring match let through: it contains every expected word while
inverting when the retry stops.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

yaml = pytest.importorskip("yaml")

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_HELPER = _ANSIBLE / "roles" / "_shared" / "tasks" / "add_apt_repository_idempotent.yml"
_MODULES = ("ansible.builtin.apt_repository", "apt_repository")
#: Each budget key, the variable it must read, and that variable's documented default.
_BUDGETS = {"retries": ("apt_repo_retries", 5), "delay": ("apt_repo_retry_delay", 10)}
_BUDGET_VARS = tuple(var for var, _ in _BUDGETS.values())
_VAR = "|".join(_BUDGET_VARS)
#: A YAML (`name:`, incl. a `- name:` list item), JSON (`"name":`) or INI inventory (`name=`)
#: assignment, at a line start or after the `{`/`,` of an inline mapping (`vars: {name: 1}`).
_ASSIGNMENT = re.compile(r"(?:^\s*(?:-\s*)?|[{,]\s*)(?:(?:" + _VAR + r')|"(?:' + _VAR + r')")\s*[:=]', re.MULTILINE)
#: Files Ansible reads variables from; ``host_group_vars`` accepts .json and extensionless too.
_VAR_FILE_SUFFIXES = {".yml", ".yaml", ".json", ".ini", ".cfg", ""}


def _add_tasks() -> list[dict]:
    """Every apt_repository task in the shared helper, loaded from YAML."""
    assert _HELPER.is_file(), (
        f"{_HELPER.relative_to(repo_root())} is missing. Seven roles include it to add apt repos; "
        "if it moved, move this guard with it rather than deleting the guard."
    )
    loaded = yaml.safe_load(_HELPER.read_text(encoding="utf-8"))
    assert isinstance(loaded, list) and loaded, "expected a non-empty Ansible task list"
    return [t for t in loaded if isinstance(t, dict) and any(m in t for m in _MODULES)]


def _budget(value, var: str) -> int | None:
    """The default N of exactly `{{ var | default(N) }}`, else None.

    A literal is refused -- it drops the documented override -- and so is a template reading
    another variable or going on to transform the default, such as
    ``{{ apt_repo_retries | default(5) | int - 4 }}``, which is not read as 5.
    """
    pattern = r"\{\{\s*" + re.escape(var) + r"\s*\|\s*default\(\s*(\d+)\s*\)\s*\}\}"
    match = re.fullmatch(pattern, str(value).strip())
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
    for key, (var, default) in _BUDGETS.items():
        if _budget(task.get(key), var) != default:
            problems.append(f"`{key}: {task.get(key)!r}` is not `{{{{ {var} | default({default}) }}}}`")
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
    "delay": "{{ apt_repo_retry_delay | default(10) }}",
}
_BROKEN = {
    "no-until": {k: v for k, v in _GOOD.items() if k != "until"},
    "negated-until": {**_GOOD, "until": "not (_r is succeeded)"},
    "foreign-until": {**_GOOD, "until": "_apt_repo_present is succeeded"},
    "no-register": {k: v for k, v in _GOOD.items() if k != "register"},
    "one-retry": {**_GOOD, "retries": "{{ apt_repo_retries | default(1) }}"},
    "untemplated-retries": {**_GOOD, "retries": "{{ apt_repo_retries }}"},
    "transformed-default": {**_GOOD, "retries": "{{ apt_repo_retries | default(5) | int - 4 }}"},
    "unwatched-variable": {**_GOOD, "retries": "{{ some_other_retries | default(5) }}"},
    "literal-retries": {**_GOOD, "retries": 5},
    "retries-read-the-delay": {**_GOOD, "retries": "{{ apt_repo_retry_delay | default(5) }}"},
    "retries-wrong-default": {**_GOOD, "retries": "{{ apt_repo_retries | default(2) }}"},
    "no-delay": {**_GOOD, "delay": 0},
    "literal-delay": {**_GOOD, "delay": 10},
    "delay-reads-the-retries": {**_GOOD, "delay": "{{ apt_repo_retries | default(10) }}"},
    "delay-wrong-default": {**_GOOD, "delay": "{{ apt_repo_retry_delay | default(1) }}"},
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


def _is_var_file(path) -> bool:
    """Whether Ansible could read variables from a file with this name."""
    return path.suffix in _VAR_FILE_SUFFIXES


def _var_files(root: Path) -> list[Path]:
    """Every file under *root*'s Ansible tree that Ansible could read variables from."""
    base = root / "autobot-slm-backend" / "ansible"
    if not base.is_dir():
        return []
    return [p for p in sorted(base.rglob("*")) if p.is_file() and _is_var_file(p)]


#: The override sweep's reach (#15826): an empty or broken walk must fail here rather than
#: report "no overrides". 342 variable files measured under the Ansible tree at declaration.
#: ``growth=40`` (~12%) because ordinary provisioning work adds role task files steadily.
REACH = declare(
    "ansible-apt-repo-budget-override-sweep",
    discover=_var_files,
    floor=342,
    growth=40,
    skips=0,
    what="Ansible variable files",
)


def _overrides(text: str, suffix: str = "") -> list[str]:
    """Assignments of a retry-budget variable in ``text``; a ``.json`` file is parsed, not pattern-matched."""
    if suffix == ".json":
        try:
            values = json.loads(text)
        except json.JSONDecodeError:
            return [m.group(0).strip() for m in _ASSIGNMENT.finditer(text)]
        return [f"{key}:" for key in _BUDGET_VARS if isinstance(values, dict) and key in values]
    return [m.group(0).strip() for m in _ASSIGNMENT.finditer(text)]


def test_no_file_overrides_the_retry_budget() -> None:
    """The budget checks above read ``default(N)``, so they hold only while nothing overrides it.

    Setting ``apt_repo_retries: 1`` in a role, ``group_vars`` or an inventory would switch the retry
    off while ``_budget`` still reads 5. Rather than evaluate Ansible, pin that the default is the
    effective value: the day an override is needed, this fails and asks for the check to follow it.
    Out of reach by construction: ``-e`` on a command line and inventories outside this tree.
    """
    scanned = REACH.examined(repo_root())
    hits = [
        f"{path.relative_to(repo_root())}: {line}"
        for path in scanned
        for line in _overrides(path.read_text(encoding="utf-8", errors="replace"), path.suffix)
    ]
    assert not hits, (
        "these override the #17230 retry budget, so the guard's `default(N)` reading is no longer the "
        "effective value -- extend the budget check to the override before keeping it:\n  " + "\n  ".join(hits)
    )


@pytest.mark.parametrize(
    "text, suffix, expected",
    [
        ("apt_repo_retries: 1\n", ".yml", 1),
        ("vars:\n  apt_repo_retry_delay: 0\n", ".yml", 1),
        ("- apt_repo_retries: 2\n", ".yml", 1),
        ("[all:vars]\napt_repo_retries=1\n", "", 1),
        ('{\n  "apt_repo_retries": 1\n}\n', ".json", 1),
        ('{"apt_repo_retry_delay": 0}', ".json", 1),
        ('{"other_var": 1}', ".json", 0),
        ("vars: {apt_repo_retries: 1}\n", ".yml", 1),
        ("vars: {a: 1, apt_repo_retry_delay: 0}\n", ".yml", 1),
        ("vars: {other_retries: 1, not_apt_repo_retries: 2}\n", ".yml", 0),
        ("#   apt_repo_retries  (int, opt.) Retry budget (default 5).\n", ".yml", 0),
        ('  retries: "{{ apt_repo_retries | default(5) }}"\n', ".yml", 0),
    ],
    ids=[
        "yaml",
        "nested-yaml",
        "list-item",
        "ini-inventory",
        "json",
        "one-line-json",
        "json-other-key",
        "inline-mapping",
        "inline-mapping-later-key",
        "inline-mapping-other-keys",
        "comment",
        "the-template-reading-it",
    ],
)
def test_the_override_detector_matches_assignments_only(text: str, suffix: str, expected: int) -> None:
    """Contrast pair: every assignment form trips it; the helper's own comment and template do not."""
    assert len(_overrides(text, suffix)) == expected, _overrides(text, suffix)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("all.yml", True),
        ("all.yaml", True),
        ("all.json", True),
        ("hosts", True),
        ("inventory.ini", True),
        ("ansible.cfg", True),
        ("README.md", False),
        ("render.py", False),
        ("site.j2", False),
    ],
)
def test_the_scan_reads_every_variable_file_type_ansible_loads(name: str, expected: bool) -> None:
    """Contrast pair for the walk's filter: host_group_vars loads .yml/.yaml/.json/extensionless files."""
    assert _is_var_file(Path(name)) is expected
