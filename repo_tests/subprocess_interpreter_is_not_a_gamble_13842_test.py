# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Spawning a subprocess must not name the interpreter as bare `python3` (#13842).

The repo floor is 3.14 (`.python-version`, and every `requires-python` agrees).
A bare `python3` resolves through PATH to whatever the box offers, which on a
developer machine is routinely older -- it is 3.10 on the one this was written
on. Two things then go wrong, and the second is worse:

* **Version.** Repo code using 3.14-only syntax is a SyntaxError at import,
  inside a subprocess, surfacing as an opaque non-zero exit. It does not look
  like a version problem; it looks like the thing being run is broken.
* **Site-packages.** PATH's interpreter has a different environment. Two NPU
  probes spawned `python3 -c "import openvino"` where only the NPU worker's
  venv has OpenVINO, so they answered "no NPU" unconditionally and would on a
  machine with a working one (#17988).

`sys.executable` is the interpreter the caller is already running under, which
is by construction the right environment. It is the established idiom here --
21 modules in `autobot-backend` alone already use it.

## Why two detectors

A literal can reach a spawn two ways, and a single pass misses one of them:

    create_subprocess_exec("python3", "-c", ...)   <- lexically inside the call
    cmd = ["python3", script]; ...; exec(*cmd)     <- assigned, then passed

Written with only the first, this guard missed the two `analytics_controller`
sites. Written with only the second, it missed the two monitoring probes. Both
run, and the union is the finding -- which is why the counts in #13842 moved
from "11 files" down to four real sites once each occurrence was classified
rather than grepped.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

#: Call targets that execute a program. `shell=True` forms are out of scope:
#: they take a string, not an argv, and belong to the shell-injection guards.
_SPAWN = frozenset(
    {
        "run",
        "Popen",
        "call",
        "check_call",
        "check_output",
        "create_subprocess_exec",
        "execv",
        "execvp",
    }
)

#: Sites that may still name a bare interpreter, with the reason. SHRINKS ONLY.
#: Each entry is a (path, reason) pair so a reader can tell a deliberate
#: exception from an unmigrated one without opening the file.
#:
#: One NPU probe remains listed, for a reason that is NOT "nobody got to it".
#: `performance_monitor.py` is now fixed: extracting its four pure dataclasses
#: to `metrics_types.py` (#16282) took it 785 -> 732, which made room for
#: `import sys`. `performance_benchmark.py` has no comparable cohesive piece
#: to lift, so it stays at its 1136 ceiling and keeps the bare interpreter. That guard is
#: explicit that a grandfathered file may not grow -- the exemption freezes
#: the size it was granted for. Splitting a 1140-line monitoring module to
#: change one argv[0] is a bigger change than the one it enables, and
#: `sys.executable` would not make these probes correct anyway: OpenVINO
#: lives only in the NPU worker's venv (#17988). So the interpreter fix rides
#: whichever change splits those files or resolves #17988, not this guard.
_PENDING: dict[str, str] = {
    "autobot-slm-backend/monitoring/performance_benchmark.py": (
        "#17988 -- NPU probe. Blocked on the file-size ceiling (1136): adding "
        "`import sys` grows a grandfathered file. sys.executable would not fix "
        "the probe anyway; the SLM venv has no OpenVINO."
    ),
}


def _bare_interpreter_spawns(tree: ast.AST) -> list[int]:
    """Line numbers where a spawn call's argv[0] is the literal `python3`."""
    found: list[int] = []
    scopes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] + [tree]

    for scope in scopes:
        # argv lists bound to a name, whose first element is the literal
        argv_vars: dict[str, int] = {}
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)) and node.value.elts:
                first = node.value.elts[0]
                if isinstance(first, ast.Constant) and first.value == "python3":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            argv_vars[target.id] = first.lineno

        for node in ast.walk(scope):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name not in _SPAWN:
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value == "python3":
                    found.append(arg.lineno)
                elif isinstance(arg, (ast.List, ast.Tuple)) and arg.elts:
                    first = arg.elts[0]
                    if isinstance(first, ast.Constant) and first.value == "python3":
                        found.append(first.lineno)
                elif isinstance(arg, ast.Name) and arg.id in argv_vars:
                    found.append(argv_vars[arg.id])
                elif isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Name) and arg.value.id in argv_vars:
                    found.append(argv_vars[arg.value.id])
    return sorted(set(found))


def _production_modules() -> list[str]:
    root = repo_root()
    found = [
        rel
        for rel in tracked_paths(
            root, "autobot-backend/**/*.py", "autobot_shared/**/*.py", "autobot-slm-backend/**/*.py"
        )
        if "_test.py" not in rel and "/tests/" not in rel and not Path(rel).name.startswith("test_")
    ]
    # Non-vacuity: an empty sweep satisfies every assertion below by looking at
    # nothing. MEASUREMENT_DISCIPLINE.md -- "nothing found" and "did not look"
    # must not read alike.
    assert len(found) > 500, f"only {len(found)} production modules swept -- the roots or filters are wrong"
    return found


def test_no_new_bare_python3_spawn() -> None:
    """A new site fails here; a listed one must carry a reason."""
    root = repo_root()
    offenders: list[str] = []
    for rel in _production_modules():
        if rel in _PENDING:
            continue
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for lineno in _bare_interpreter_spawns(tree):
            offenders.append(f"{rel}:{lineno}")

    assert not offenders, (
        f"{len(offenders)} subprocess spawn(s) name the interpreter as bare `python3`:\n  "
        + "\n  ".join(offenders)
        + "\n\nUse `sys.executable`. PATH's `python3` is a gamble on BOTH the version (the repo "
        "floor is 3.14; 3.10 is common on a dev box) and the site-packages (#17988: two NPU "
        "probes answered 'no' forever because the interpreter they picked had no OpenVINO)."
    )


def test_the_pending_list_only_shrinks() -> None:
    """Direction, not agreement (#17970).

    Compared against the LIVE tree rather than a mirrored record, so an entry
    whose site has been migrated must be deleted here or this fails. A
    mirrored pair would show two agreeing numbers and nothing wrong.
    """
    root = repo_root()
    stale = [
        rel for rel in _PENDING if not _bare_interpreter_spawns(ast.parse((root / rel).read_text(encoding="utf-8")))
    ]
    assert not stale, (
        f"{len(stale)} entr(y/ies) in `_PENDING` no longer spawn a bare interpreter:\n  "
        + "\n  ".join(stale)
        + "\n\nDelete them. The list is a ratchet; a spent entry is cover for a future one."
    )


def test_every_pending_entry_states_its_reason() -> None:
    """An exemption without a reason is indistinguishable from an oversight."""
    missing = [rel for rel, why in _PENDING.items() if not why.strip() or "#" not in why]
    assert not missing, f"pending entries with no issue reference: {missing}"


_INLINE = 'import asyncio\nasyncio.create_subprocess_exec("python3", "-c", "x")\n'
_VIA_LIST = 'import subprocess\ncmd = ["python3", "s.py"]\nsubprocess.run(cmd)\n'
_VIA_STAR = 'import asyncio\ncmd = ["python3", "s.py"]\nasyncio.create_subprocess_exec(*cmd)\n'
_SYS_EXEC = 'import subprocess, sys\nsubprocess.run([sys.executable, "s.py"])\n'
_NAME_LIST = 'TOOLS = ["bash", "python3", "node"]\n'
_NOT_FIRST = 'import subprocess\nsubprocess.run(["env", "python3", "s.py"])\n'


@pytest.mark.parametrize(
    "label,source,expected",
    [
        ("inline argv[0]", _INLINE, 1),
        ("a list bound to a name", _VIA_LIST, 1),
        ("the same list splatted", _VIA_STAR, 1),
        ("sys.executable", _SYS_EXEC, 0),
        ("a plain list of tool names", _NAME_LIST, 0),
        ("python3 that is not argv[0]", _NOT_FIRST, 0),
    ],
)
def test_the_detector_separates_the_shapes(label: str, source: str, expected: int) -> None:
    """The contrast set, with both false-positive shapes.

    `_NAME_LIST` is the common one -- `sandbox.py`, `deployments.py` and
    `mcp_launcher_allowlist` all list `python3` as a tool NAME, and flagging
    those would make the guard noisy enough to be muted. `_NOT_FIRST` guards
    the other direction: `env python3 s.py` runs python3, but argv[0] is
    `env`, and this detector is deliberately about argv[0] only -- stated
    rather than left for a reader to discover.
    """
    assert len(_bare_interpreter_spawns(ast.parse(source))) == expected, label
