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
#: EMPTY, and that took three attempts to earn. Both NPU probes were listed
#: here as "blocked by the file-size ceiling" -- each file is grandfathered
#: and `import sys` would grow it. That was true and it was the wrong unit of
#: work: both modules held pure `@dataclass` records with no external
#: importers, and lifting those to `metrics_types.py` and `benchmark_types.py`
#: (#16282) freed far more room than the fix needed.
#:
#: Worth keeping because the mistake is reusable: I accepted my own "blocked"
#: three times before looking at the files' structure. A blocker deserves the
#: same scrutiny as a green test.
#:
#: Neither extraction makes the probes CORRECT -- OpenVINO lives only in the
#: NPU worker's venv, so both still answer "no NPU" unconditionally (#17988).
#: Naming the interpreter only stops the answer depending on PATH.
#:
#: KEYED BY OCCURRENCE, NOT BY FILE (CodeRabbit, #13916). A file-keyed
#: exemption hides every NEW spawn in a listed file, and the staleness check
#: below would still pass because *some* spawn remained. The key is
#: ``"<path>:<lineno>"``.
_PENDING: dict[str, str] = {}


def _scope_nodes(scope: ast.AST):
    """Nodes belonging to *scope*, not descending into a nested scope.

    `ast.walk` from the module would collect a nested function's assignments as
    though they bound names in the enclosing scope (CodeRabbit, #13916).
    """
    stack = list(getattr(scope, "body", []))
    while stack:
        node = stack.pop(0)
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # Its BODY is a different scope, so it is not walked here. Its
            # decorators and argument defaults ARE evaluated in this scope.
            stack.extend(node.decorator_list)
            stack.extend(getattr(getattr(node, "args", None), "defaults", []) or [])
            continue
        if isinstance(node, ast.Lambda):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _bare_interpreter_spawns(tree: ast.AST) -> list[int]:
    """Line numbers where a spawn call's argv[0] is the literal `python3`.

    BINDINGS RESOLVE IN STATEMENT ORDER (CodeRabbit, #13916). Collecting every
    binding first and then examining calls reports a stale one: for
    ``cmd = ["python3"]; cmd = [sys.executable]; subprocess.run(cmd)`` the spawn
    uses `sys.executable`, and a set-of-all-bindings detector still flags it.
    The binding that counts is the last one at or above the call's line.
    """
    found: list[int] = []
    scopes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] + [tree]

    for scope in scopes:
        # name -> [(lineno, is_bare_python3), ...], in source order
        bindings: dict[str, list[tuple[int, bool]]] = {}
        for node in _scope_nodes(scope):
            if not isinstance(node, ast.Assign):
                continue
            bare, at = False, node.lineno
            if isinstance(node.value, (ast.List, ast.Tuple)) and node.value.elts:
                first = node.value.elts[0]
                if isinstance(first, ast.Constant) and first.value == "python3":
                    bare, at = True, first.lineno
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bindings.setdefault(target.id, []).append((at, bare))

        def _binding_in_effect(name: str, call_line: int) -> int | None:
            """The line of the bare-`python3` binding governing a call, if any."""
            prior = [(at, bare) for at, bare in bindings.get(name, []) if at <= call_line]
            if not prior:
                return None
            at, bare = prior[-1]
            return at if bare else None

        for node in _scope_nodes(scope):
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
                elif isinstance(arg, ast.Name):
                    at = _binding_in_effect(arg.id, node.lineno)
                    if at is not None:
                        found.append(at)
                elif isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Name):
                    at = _binding_in_effect(arg.value.id, node.lineno)
                    if at is not None:
                        found.append(at)
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
    #
    # This floor binds to DISCOVERY only; the floor that binds to REACH is in
    # `_parsed_production_modules`, because a path that fails to parse is a
    # file this guard did not examine (CodeRabbit, #13916).
    assert len(found) > 500, f"only {len(found)} production modules swept -- the roots or filters are wrong"
    return found


def _parsed_production_modules() -> list[tuple[str, ast.AST]]:
    """Every production module, PARSED -- an unparseable one is a failure, not a skip.

    `len(discovered)` is a claim about the filesystem walk. The guard's reach is
    the number of files it actually parsed, and the two differ precisely when
    `ast.parse` raises -- the case where a silent `continue` let a file escape
    the guard while still counting toward the floor (CodeRabbit, #13916).
    """
    root = repo_root()
    parsed: list[tuple[str, ast.AST]] = []
    unreadable: list[str] = []
    for rel in _production_modules():
        try:
            parsed.append((rel, ast.parse((root / rel).read_text(encoding="utf-8"))))
        except (OSError, SyntaxError, UnicodeDecodeError) as exc:
            unreadable.append(f"{rel}: {type(exc).__name__}: {exc}")

    assert not unreadable, (
        f"{len(unreadable)} production module(s) could not be parsed, so this guard did not "
        "examine them:\n  " + "\n  ".join(unreadable) + "\n\nAn unreadable file is a "
        "violation, not a skip -- skipping it reports 'no bare spawn' about a file nobody read."
    )
    assert len(parsed) > 500, f"only {len(parsed)} production modules PARSED -- the guard's reach collapsed"
    return parsed


def test_no_new_bare_python3_spawn() -> None:
    """A new site fails here; a listed one must carry a reason."""
    offenders: list[str] = []
    for rel, tree in _parsed_production_modules():
        for lineno in _bare_interpreter_spawns(tree):
            occurrence = f"{rel}:{lineno}"
            if occurrence in _PENDING:
                continue
            offenders.append(occurrence)

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
    stale: list[str] = []
    for occurrence in _PENDING:
        rel, _, lineno = occurrence.rpartition(":")
        live = _bare_interpreter_spawns(ast.parse((root / rel).read_text(encoding="utf-8")))
        # The EXACT occurrence must still be live. Checking only "does this file
        # still spawn" would keep an entry alive on the strength of a different
        # spawn, which is the same hole as exempting by file (CodeRabbit, #13916).
        if int(lineno) not in live:
            stale.append(occurrence)

    assert not stale, (
        f"{len(stale)} entr(y/ies) in `_PENDING` no longer spawn a bare interpreter at that line:\n  "
        + "\n  ".join(stale)
        + "\n\nDelete them. The list is a ratchet; a spent entry is cover for a future one."
    )


def test_every_pending_entry_states_its_reason() -> None:
    """An exemption without a reason is indistinguishable from an oversight."""
    missing = [occ for occ, why in _PENDING.items() if not why.strip() or "#" not in why]
    assert not missing, f"pending entries with no issue reference: {missing}"


_INLINE = 'import asyncio\nasyncio.create_subprocess_exec("python3", "-c", "x")\n'
_VIA_LIST = 'import subprocess\ncmd = ["python3", "s.py"]\nsubprocess.run(cmd)\n'
_VIA_STAR = 'import asyncio\ncmd = ["python3", "s.py"]\nasyncio.create_subprocess_exec(*cmd)\n'
_SYS_EXEC = 'import subprocess, sys\nsubprocess.run([sys.executable, "s.py"])\n'
_NAME_LIST = 'TOOLS = ["bash", "python3", "node"]\n'
_NOT_FIRST = 'import subprocess\nsubprocess.run(["env", "python3", "s.py"])\n'

#: CodeRabbit (#13916): the three shapes a set-of-all-bindings detector gets
#: wrong. Each one PASSED before the statement-order rewrite.
_REBOUND_SAFE = 'import subprocess, sys\ncmd = ["python3"]\ncmd = [sys.executable]\nsubprocess.run(cmd)\n'
_REBOUND_BARE = 'import subprocess, sys\ncmd = [sys.executable]\ncmd = ["python3"]\nsubprocess.run(cmd)\n'
_NESTED_BINDING = 'import subprocess\ndef inner():\n    cmd = ["python3"]\n    return cmd\nsubprocess.run(cmd)\n'
#: The contrast for the one above -- scope isolation must not blind the guard
#: to a spawn that really is inside the nested function.
_NESTED_SPAWN = 'import subprocess\ndef inner():\n    cmd = ["python3"]\n    subprocess.run(cmd)\n'


@pytest.mark.parametrize(
    "label,source,expected",
    [
        ("inline argv[0]", _INLINE, 1),
        ("a list bound to a name", _VIA_LIST, 1),
        ("the same list splatted", _VIA_STAR, 1),
        ("sys.executable", _SYS_EXEC, 0),
        ("a plain list of tool names", _NAME_LIST, 0),
        ("python3 that is not argv[0]", _NOT_FIRST, 0),
        ("rebound to sys.executable before the spawn", _REBOUND_SAFE, 0),
        ("rebound to bare python3 before the spawn", _REBOUND_BARE, 1),
        ("a nested function's binding does not leak out", _NESTED_BINDING, 0),
        ("a spawn inside that nested function is still seen", _NESTED_SPAWN, 1),
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
