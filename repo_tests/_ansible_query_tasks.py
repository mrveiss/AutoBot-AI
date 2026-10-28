# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Find read-only status-query tasks in Ansible YAML (#19663).

A `command`/`shell` task is skipped under `--check`, so a query whose result a later
task reads leaves that result undefined and the dry run dies. Read-only queries are safe
to run in check mode, and must say so with `check_mode: false`.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

import yaml

_EXEC_MODULES = ("command", "shell", "ansible.builtin.command", "ansible.builtin.shell")
#: The query commands. Anchored at the start of the command: a mutating command that
#: merely mentions one (`apt-get install ... && dpkg-query`) is not a query task.
_QUERY = re.compile(
    r"^(?:dpkg-query\b"
    r"|apt-cache\s+policy\b"
    r"|systemctl\s+(?:--\S+\s+)*is-(?:active|enabled)\b"
    r"|rpm\s+-q"
    r"|(?:\{\{[^}]*\}\}|[^\s{])+\s+--version\b)"
)
#: The binary token is a template (`{{ x }}`, no nested braces) or non-space, non-brace characters:
#: the two alternatives cannot match the same character, so the repeat cannot backtrack exponentially.
#: A command chained with `;`, `&&`, `||`, a redirect, or a command substitution may do more than query.
#: Stderr redirection is not a write that matters to the verdict.
_STDERR_REDIRECT = re.compile(r"\s2>(?:&1|/dev/null)")
#: `|| true` after a query only swallows its exit code; it adds no second command.
_TRAILING_OR_TRUE = re.compile(r"\s*\|\|\s*true\s*$")
#: Output filters that read and never write: a query piped through one is still a query.
_READONLY_FILTER = re.compile(r"\s*\|\s*(?:grep|head|tail|cut|sort|wc|tr)\b[^|;&<>]*")
#: Any second command or a pipe into anything else (`| xargs apt-get remove`, a backgrounded `&`).
#: A Jinja expression is data, not shell: its filter pipes (`{{ x | join(' ') }}`) are not a pipeline.
_JINJA = re.compile(r"\{\{[^}]*\}\}")
_CHAINED = re.compile(r"\n|;|&|\||>|`|\$\(")


def _command_text(module_value: Any) -> str:
    """The command string of an exec-module value (free-form, `cmd:` or `argv:`)."""
    if isinstance(module_value, str):
        return module_value
    if isinstance(module_value, dict):
        if "cmd" in module_value:
            return str(module_value["cmd"])
        if isinstance(module_value.get("argv"), list):
            return " ".join(str(a) for a in module_value["argv"])
    return ""


def is_status_query(task: dict) -> bool:
    """Whether *task* is a read-only status query by its command."""
    for module in _EXEC_MODULES:
        if module in task:
            text = _JINJA.sub("JINJA", _command_text(task[module])).replace("\\\n", " ").strip()
            text = _TRAILING_OR_TRUE.sub("", _STDERR_REDIRECT.sub("", text)).strip()
            text = _READONLY_FILTER.sub("", text).strip()
            if _CHAINED.search(text):
                return False
            return bool(_QUERY.match(text))
    return False


#: The marker for a verify-after-install query: it runs only when the play is really executing.
VERIFY_MARKER = "not ansible_check_mode"


def is_verify_after_install(task: dict) -> bool:
    """A query that checks the RESULT of an install/start earlier in the play.

    Under `--check` that install is skipped, so on an unprovisioned host the query would fail the
    dry run. Such a task must NOT run in check mode: it says so with `when: not ansible_check_mode`
    (alone or as one element of a `when:` list). A probe-then-act query, whose registered result
    decides a later task, is the opposite and carries `check_mode: false` instead.
    """
    when = task.get("when")
    conditions = when if isinstance(when, list) else [when]
    return any(isinstance(c, str) and c.strip() == VERIFY_MARKER for c in conditions)


def is_check_safe(task: dict) -> bool:
    """A query task is acceptable: a probe in check mode, or a marked verify-after-install."""
    if is_verify_after_install(task):
        return task.get("changed_when") is False and task.get("check_mode") is not False
    return has_check_mode_off(task)


def has_check_mode_off(task: dict) -> bool:
    """`check_mode: false` and `changed_when: false` both present."""
    return task.get("check_mode") is False and task.get("changed_when") is False


def iter_tasks(node: Any) -> Iterator[dict]:
    """Every mapping in a loaded YAML document that is a task carrying an exec module."""
    if isinstance(node, dict):
        if any(m in node for m in _EXEC_MODULES):
            yield node
        for value in node.values():
            yield from iter_tasks(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_tasks(item)


def query_tasks(text: str) -> list[dict]:
    """Status-query tasks in a YAML document; unparseable (templated) files yield none."""
    try:
        docs = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return []
    return [t for doc in docs for t in iter_tasks(doc) if is_status_query(t)]
