# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A remote command string interpolates only quoted values, ints and constants (#18359).

`service_name` was a URL path parameter interpolated into `sudo -n systemctl <action> <name>`
and `journalctl -u <name>`, run by a shell on a fleet node. The defect CLASS is "a string built
for a remote shell with an unquoted interpolation", so this guard reads the syntax tree of the
files that build such strings: any f-string, `.format` or `%` whose literal text names
`sudo` / `systemctl` / `journalctl` / `ssh` / `bash -c` / `sh -c` may interpolate only

* a `shlex.quote(...)` result,
* an `int(...)` / `len(...)` result, or
* a module-level constant (an UPPER_CASE name or attribute),

or carry a recorded allowance in `_ALLOWED` with its reason. There is no silent exemption.
Docstrings and logging-call arguments describe a command rather than issue one and are skipped.
The scanned files are an explicit list, not a discovered population, so this declares no reach.
"""

from __future__ import annotations

import ast
import re

import pytest
from repo_tests._paths import repo_root

_SCANNED = (
    "autobot-slm-backend/services/service_restart.py",
    "autobot-slm-backend/services/journal_fetch.py",
    "autobot-slm-backend/services/service_orchestrator.py",
    "autobot-slm-backend/services/code_distributor.py",
    "autobot-slm-backend/api/services.py",
)
_REMOTE_WORDS = re.compile(r"\b(?:sudo|systemctl|journalctl|ssh|bash\s+-c|sh\s+-c)\b")
_LOG_METHODS = frozenset({"debug", "info", "warning", "error", "exception", "critical", "log"})

#: (file, interpolated expression source) -> why it is safe. A new entry needs a reason a reviewer accepts.
_ALLOWED: dict[tuple[str, str], str] = {
    (
        "autobot-slm-backend/services/code_distributor.py",
        "ssh_port",
    ): "an int port from the node row, typed `int` on every caller; reaches the LOCAL ssh argv option string",
    (
        "autobot-slm-backend/services/journal_fetch.py",
        "bounded",
    ): "`max(1, min(int(lines), JOURNAL_MAX_LINES))`, computed one line above: an int",
    (
        "autobot-slm-backend/services/service_orchestrator.py",
        "command",
    ): "only ServiceDefinition.start_command/stop_command (static module-level definitions) and "
    "systemctl_remote_command() results reach _execute_ssh; none is request input",
    (
        "autobot-slm-backend/api/services.py",
        "port",
    ): "an int taken from SERVICE_PORT_MAP, never from the request",
    (
        "autobot-slm-backend/services/service_restart.py",
        "sudo",
    ): "`sudo -n` or `sudo`, selected from a bool two lines above",
    (
        "autobot-slm-backend/services/service_restart.py",
        "action",
    ): "checked against ALLOWED_SYSTEMCTL_ACTIONS before the f-string is reached",
    (
        "autobot-slm-backend/services/service_restart.py",
        "tail",
    ): "` || true` or empty, selected from a bool",
    (
        "autobot-slm-backend/services/service_restart.py",
        "quoted",
    ): "built from shlex.quote(validate_unit_name(u)) in the line above",
}


def _is_constant_name(node: ast.AST) -> bool:
    name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
    return bool(name) and name.upper() == name and name[0].isalpha()


def _is_safe(expr: ast.AST) -> bool:
    """`shlex.quote(...)`, `int(...)`/`len(...)`, or a module-level constant."""
    if isinstance(expr, ast.Call):
        fn = expr.func
        if isinstance(fn, ast.Attribute) and fn.attr == "quote" and isinstance(fn.value, ast.Name):
            return fn.value.id == "shlex"
        return isinstance(fn, ast.Name) and fn.id in {"int", "len"}
    return _is_constant_name(expr)


def _skipped_ids(tree: ast.AST) -> set[int]:
    """Docstrings and everything passed to a logging call."""
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                skipped.add(id(node.body[0].value))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _LOG_METHODS:
            for arg in [*node.args, *(k.value for k in node.keywords)]:
                skipped.update(id(n) for n in ast.walk(arg))
    return skipped


def _literal_text(parts: list[ast.AST]) -> str:
    return " ".join(p.value for p in parts if isinstance(p, ast.Constant) and isinstance(p.value, str))


def _interpolations(node: ast.AST) -> tuple[str, list[ast.AST]] | None:
    """(literal text, interpolated expressions) for an f-string, `.format` call or `%` expression."""
    if isinstance(node, ast.JoinedStr):
        exprs = [v.value for v in node.values if isinstance(v, ast.FormattedValue)]
        return _literal_text(node.values), exprs
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        base = node.func.value
        if isinstance(base, ast.Constant) and isinstance(base.value, str):
            return base.value, [*node.args, *(k.value for k in node.keywords)]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            right = node.right
            return node.left.value, list(right.elts) if isinstance(right, ast.Tuple) else [right]
    return None


def unsafe_interpolations(source: str, rel: str) -> list[str]:
    """Every interpolation into a remote-command string that is neither safe nor allowed."""
    tree = ast.parse(source)
    skipped = _skipped_ids(tree)
    bad: list[str] = []
    for node in ast.walk(tree):
        found = None if id(node) in skipped else _interpolations(node)
        if found is None or not _REMOTE_WORDS.search(found[0]):
            continue
        for expr in found[1]:
            text = ast.unparse(expr)
            if not _is_safe(expr) and (rel, text) not in _ALLOWED:
                bad.append(f"{rel}:{node.lineno}: {{{text}}}")
    return bad


@pytest.mark.parametrize("rel", _SCANNED)
def test_remote_command_strings_interpolate_only_quoted_ints_and_constants(rel: str) -> None:
    path = repo_root() / rel
    assert path.is_file(), f"{rel} is named by the guard and does not exist"
    assert unsafe_interpolations(path.read_text(encoding="utf-8"), rel) == []


def test_every_allowance_is_still_needed() -> None:
    """An allowance with no matching site is dead and hides the next one that reuses its spelling."""
    used: set[tuple[str, str]] = set()
    for rel in _SCANNED:
        tree = ast.parse((repo_root() / rel).read_text(encoding="utf-8"))
        skipped = _skipped_ids(tree)
        for node in ast.walk(tree):
            found = None if id(node) in skipped else _interpolations(node)
            if found and _REMOTE_WORDS.search(found[0]):
                used.update((rel, ast.unparse(e)) for e in found[1])
    assert set(_ALLOWED) <= used, sorted(set(_ALLOWED) - used)


@pytest.mark.parametrize(
    ("label", "source", "expected_bad"),
    [
        ("an unquoted name (the defect)", 'cmd = f"sudo -n systemctl restart {service_name}"\n', 1),
        ("an unquoted name in journalctl", 'cmd = f"journalctl -u {svc} -n 5"\n', 1),
        ("a .format", 'cmd = "sudo systemctl stop {}".format(name)\n', 1),
        ("a % expression", 'cmd = "sudo systemctl stop %s" % name\n', 1),
        ("an unquoted ssh_user", 'cmd = f"ssh {user}@host"\n', 1),
        ("a quoted name", 'cmd = f"sudo -n systemctl restart -- {shlex.quote(service_name)}"\n', 0),
        ("an int", 'cmd = f"sudo journalctl -n {int(lines)}"\n', 0),
        ("a module constant", 'cmd = f"sudo tee {REMOTE_PATH} && ssh {mod.KEY_PATH}"\n', 0),
        ("prose in a log call", 'logger.info(f"ran sudo systemctl {name}")\n', 0),
        ("no remote word", 'msg = f"restarting {name}"\n', 0),
        ("a docstring", 'def f():\n    """sudo systemctl {name}"""\n', 0),
    ],
)
def test_the_detector_has_contrast_fixtures(label: str, source: str, expected_bad: int) -> None:
    assert len(unsafe_interpolations(source, "fixture.py")) == expected_bad, label
