# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One executor builds the SSH `systemctl` command (#18186, under #17452).

Restarting units on a node over SSH was written three times in the SLM backend, with different
`sudo -n`, timeout and failure handling. The command is now built once, by
`run_systemctl_over_ssh` in `autobot-slm-backend/services/service_restart.py`; the three sites
keep their current flags through explicit parameters (unifying them is the owner decision on
#17455).

The marker is a REMOTE shell command string: `sudo [-n] systemctl <restart|start|stop|{action}>`,
as a literal or an f-string. A local systemctl call is a different concept and is not matched:
`api/code_sync.py` runs it as an argv list (`"systemctl"`, `"restart"`, ... as separate elements,
no `sudo` in the string), so it never forms this command string. The detector reads the syntax
tree, so a comment is not a command, and docstrings and log-call arguments are skipped because
they describe a restart rather than issue one.

The four other SSH sites found while writing the first version (backup, blue_green,
code_distributor, service_orchestrator) were moved onto the executor in the same issue, so there is
no allowance list: the set of builders outside the executor is empty, and stays empty.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot-slm-backend/services/service_restart.py"

#: `sudo [-n] systemctl <verb>`, or `{sudo} systemctl <verb>` once an f-string is flattened to `{}`.
_COMMAND = re.compile(r"(?:\bsudo\s+(?:-n\s+)?|\{\}\s+)systemctl\s+(?:restart|start|stop|\{\})")
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical", "log"})


def _flatten(node: ast.AST) -> str | None:
    """The text of a string literal or f-string, with each interpolation as `{}`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}" for v in node.values
        )
    return None


def _skipped_ids(tree: ast.AST) -> set[int]:
    """Docstrings, and everything passed to a logging call: prose about a restart, not one."""
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                skipped.add(id(body[0].value))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _LOG_METHODS:
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                skipped.update(id(n) for n in ast.walk(arg))
    return skipped


def _builds_remote_systemctl(source: str) -> bool:
    """True when `source` contains a remote `sudo [-n] systemctl <verb>` command string."""
    tree = ast.parse(source)
    skipped = _skipped_ids(tree)
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        text = _flatten(node)
        if text is not None and _COMMAND.search(text):
            return True
    return False


def _is_source_python(rel: str) -> bool:
    """A non-test Python file: the only kind that can build the command."""
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("autobot-slm-backend/services/service_restart.py", True),
        ("autobot-slm-backend/services/service_restart_test.py", False),
        ("autobot-slm-backend/tests/api/test_roles.py", False),
        ("autobot-slm-backend/tests/conftest.py", False),
        ("autobot-slm-backend/api/roles.py", True),
        ("autobot-slm-backend/api/roles.md", False),
    ],
)
def test_the_test_path_filter_skips_tests_and_keeps_source(rel: str, expected: bool) -> None:
    assert _is_source_python(rel) is expected


def _source_population(root: Path) -> list[str]:
    """Non-test Python source in the SLM backend: the scan's whole input."""
    try:
        tracked = tracked_paths(root, "autobot-slm-backend")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "ssh-restart-executor-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=217,
    what="non-test slm-backend python source",
    roots=("autobot-slm-backend",),
    growth=100,
)


@functools.lru_cache(maxsize=1)
def _builders() -> tuple[tuple[str, ...], int]:
    """Files outside the executor that build the command, and how many files were parsed."""
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if "systemctl" not in source:
            continue
        parsed += 1
        if rel != _CANONICAL and _builds_remote_systemctl(source):
            found.append(rel)
    return tuple(found), parsed


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a sudo -n restart (the contrast positive)", 'cmd = f"sudo -n systemctl restart {u}"\n', True),
        ("a sudo restart with no -n", 'cmd = "sudo systemctl restart a"\n', True),
        ("a templated action", 'cmd = f"sudo -n systemctl {action} {svc}"\n', True),
        ("a templated sudo prefix", 'cmd = f"{sudo} systemctl {action} {units}"\n', True),
        ("a stop", 'run("sudo systemctl stop a")\n', True),
        ("a comment naming it", "# sudo -n systemctl restart a\nx = 1\n", False),
        ("a docstring naming it", 'def f():\n    """Runs sudo -n systemctl restart a."""\n', False),
        ("a log message about restarting", 'logger.info("ran sudo systemctl restart %s", u)\n', False),
        ("a local argv list", 'argv = ["systemctl", "restart", "u"]\n', False),
        ("a user-scope command", 'cmd = f"systemctl --user {action} {svc}"\n', False),
        ("a status query", 'cmd = "sudo systemctl is-active a"\n', False),
    ],
)
def test_the_matcher_tells_a_command_from_a_mention(label: str, source: str, expected: bool) -> None:
    assert _builds_remote_systemctl(source) is expected, label


def test_the_executor_module_itself_builds_the_command() -> None:
    """The negative the guard excludes by path: the module that owns the command must match it."""
    assert _builds_remote_systemctl((repo_root() / _CANONICAL).read_text(encoding="utf-8")) is True


def test_the_scan_is_not_vacuous() -> None:
    """The executor and the sites that call it mention systemctl; fewer parsed is a blind scan."""
    _, parsed = _builders()
    assert parsed >= 5, f"parsed {parsed} files mentioning systemctl"


def test_only_the_executor_builds_the_ssh_systemctl_command() -> None:
    found, _ = _builders()
    assert not found, (
        f"#18186: {list(found)} build a remote `sudo [-n] systemctl <action>` command. The command is built once, "
        f"by run_systemctl_over_ssh in {_CANONICAL}; call it with explicit use_noninteractive_sudo and timeout."
    )
