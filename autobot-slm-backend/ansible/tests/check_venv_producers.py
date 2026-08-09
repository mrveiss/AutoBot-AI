#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: one venv path is never built by two interpreters (#13746).

Three producers built ``/opt/autobot/venv`` — ``roles/backend_services`` and the
``aiml`` play with python3.14, the ``npu`` play with python3.11. Co-location is a
supported layout (the role-facts test inventory covers a single host carrying
several roles), so those producers can land on one machine. The last one to run
rewrites ``pyvenv.cfg`` while ``site-packages`` still holds binaries built by the
other interpreter.

That failure never surfaces as a deploy error. It surfaces as a native-extension
``ImportError`` at service startup, long after Ansible reported success — which
is why this is checked statically rather than left to a smoke test.

Run from the ansible directory:  python3 tests/check_venv_producers.py
"""

import pathlib
import re
import sys

_EXCLUDE_DIRS = (".worktrees", ".git", "node_modules", "__pycache__")

# `python3.14 -m venv <path>`, in a shell: or command: line. The path runs to
# end of line rather than \S+ because it is often a Jinja expression containing
# spaces (`{{ npu_install_dir }}/venv`), which \S+ truncates to `{{`.
_SHELL_VENV = re.compile(r"(?P<py>python3\.\d+)\s+-m\s+venv\s+(?P<path>.+?)\s*$")
# A `cd` earlier in the same shell block makes the venv argument relative.
_CD = re.compile(r"^\s*cd\s+(?P<dir>\S+)\s*$")
# The pip module's explicit pairing of a venv with an interpreter.
_VIRTUALENV = re.compile(r"^\s*virtualenv:\s*(?P<path>\S+)\s*$")
_VIRTUALENV_PY = re.compile(r"^\s*virtualenv_python:\s*(?P<py>\S+)\s*$")


def _clean(value: str) -> str:
    """Normalise a venv path so the same target compares equal everywhere.

    Quotes are stripped, and whitespace inside a Jinja expression is collapsed —
    `{{ npu_install_dir }}/venv` and `{{npu_install_dir}}/venv` are one path.
    """
    value = value.strip().strip("\"'").strip()
    return re.sub(r"\{\{\s*(.*?)\s*\}\}", r"{{\1}}", value)


def _resolve(path: str, cwd: str | None) -> str:
    """Make a venv argument absolute using the `cd` that preceded it."""
    if path.startswith("/") or path.startswith("{{") or cwd is None:
        return path
    return f"{cwd.rstrip('/')}/{path}"


def _ansible_yaml(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(
        p
        for p in root.rglob("*.y*ml")
        if not any(part in _EXCLUDE_DIRS for part in p.relative_to(root).parts)
    )


def venv_producers(root: pathlib.Path) -> dict[str, set]:
    """Return ``{venv path: {(interpreter, "file:line")}}`` for every producer."""
    producers: dict[str, set] = {}
    for path in _ansible_yaml(root):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        rel = path.relative_to(root)
        pending_venv = None
        cwd = None
        for line_no, line in enumerate(lines, 1):
            if match := _CD.match(line):
                cwd = _clean(match.group("dir"))
            if match := _SHELL_VENV.search(line):
                venv = _resolve(_clean(match.group("path")), cwd)
                producers.setdefault(venv, set()).add((match.group("py"), f"{rel}:{line_no}"))
            if match := _VIRTUALENV.match(line):
                pending_venv = (_clean(match.group("path")), line_no)
            elif (match := _VIRTUALENV_PY.match(line)) and pending_venv:
                venv, venv_line = pending_venv
                producers.setdefault(venv, set()).add((_clean(match.group("py")), f"{rel}:{venv_line}"))
                pending_venv = None
    return producers


def main() -> int:
    """Fail when any venv path is claimed by more than one interpreter."""
    root = pathlib.Path(".").resolve()
    producers = venv_producers(root)

    conflicts = {
        venv: sites for venv, sites in producers.items() if len({py for py, _ in sites}) > 1
    }

    if conflicts:
        print("A venv path is built by more than one interpreter:")
        for venv, sites in sorted(conflicts.items()):
            print(f"  {venv}")
            for py, where in sorted(sites, key=lambda s: s[1]):
                print(f"    {py:<12} {where}")
        print("\nCo-location puts these on one host, where the last producer rewrites")
        print("pyvenv.cfg over site-packages built by the other. The failure is a")
        print("native ImportError at startup, not a deploy error.")
        return 1

    print(f"check_venv_producers: {len(producers)} venv path(s), each with a single interpreter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
