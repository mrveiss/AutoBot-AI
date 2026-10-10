# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One result mapping for a synchronous command (#18180).

`autobot-backend/utils/command_utils.py` owns what a command's outcome looks like: decode with
`errors="replace"`, strip ANSI, `TimeoutExpired` -> `status="timeout"`, `FileNotFoundError` ->
127. The async path has always used it; `execute_command_sync` is its synchronous twin, built
from the same helpers. A function that calls `subprocess.run` and then maps the outcome into its
own dict, tuple or `CommandResult` is a second implementation of that mapping.

The marker is one function that BOTH calls `subprocess.run` AND either (a) has an `except`
handler that returns a dict, a tuple or a `CommandResult(...)`, or (b) calls
`.decode(..., errors=...)`. A probe that answers a bool, `None`, `""` or a list is not a result
mapping and is not flagged: it is a plain call interpreted by its own caller.

`_KNOWN` freezes the functions that already do this. It only DROPS: migrating one fails
`test_every_known_site_still_maps_its_own_result` until its entry is deleted, and adding one is
refused by `test_no_new_hand_rolled_result_mapping`. They stay because moving them changes what
their callers see (env merged rather than replaced, stdout stripped and ANSI-cleaned, exit codes
127/-1 for not-found/timeout) -- an owner decision recorded on #18180, not a refactor.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot-backend/utils/command_utils.py"

#: path -> functions that call subprocess.run and map the outcome themselves (#18180 AC1).
_KNOWN: dict[str, frozenset[str]] = {
    "autobot-backend/agents/ac_poster.py": frozenset({"_run_gh_capture", "_run_gh"}),
    "autobot-backend/api/vnc_manager.py": frozenset({"start_vnc_server", "_run_xdotool_cmd"}),
    "autobot-backend/pki/generator.py": frozenset({"_run_openssl_command"}),
    "autobot-backend/system_integration.py": frozenset({"_run_command"}),
    "autobot-backend/tools/code_interpreter.py": frozenset({"execute_code"}),
    "autobot-backend/utils/timeout_migration_examples.py": frozenset({"_run_single_test"}),
    "autobot-backend/workers/audit_tasks.py": frozenset({"_run"}),
}

_RESULT_NODES = (ast.Dict, ast.Tuple)


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _own_nodes(fn: ast.AST):
    """Nodes of `fn` excluding nested function bodies: each function is judged on its own."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(node))


def _is_subprocess_run(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
    )


def _is_result_value(value: ast.AST | None) -> bool:
    if isinstance(value, _RESULT_NODES):
        return True
    return isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "CommandResult"


def _handler_returns_a_result(handler: ast.ExceptHandler) -> bool:
    return any(isinstance(n, ast.Return) and _is_result_value(n.value) for n in ast.walk(handler))


def _decodes_with_errors(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "decode"
        and any(kw.arg == "errors" for kw in node.keywords)
    )


def _mapping_functions(source: str) -> set[str]:
    """Names of functions that call `subprocess.run` and map the outcome into their own result."""
    found: set[str] = set()
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        own = list(_own_nodes(fn))
        if not any(_is_subprocess_run(n) for n in own):
            continue
        handlers = [n for n in own if isinstance(n, ast.ExceptHandler)]
        if any(_handler_returns_a_result(h) for h in handlers) or any(_decodes_with_errors(n) for n in own):
            found.add(fn.name)
    return found


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "sync-command-result-mapping-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=2359,
    what="non-test python source",
    roots=("autobot-backend",),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _sites() -> tuple[dict[str, frozenset[str]], int]:
    """Mapping functions per file, and how many files mentioning `subprocess.run` were parsed."""
    found: dict[str, frozenset[str]] = {}
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if "subprocess.run" not in source:
            continue
        parsed += 1
        names = _mapping_functions(source)
        if names:
            found[rel] = frozenset(names)
    return found, parsed


_DICT_MAPPING = """
import subprocess
def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True)
        return {"status": "success", "output": r.stdout}
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
"""
_TUPLE_MAPPING = """
import subprocess
def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True)
        return r.returncode, r.stdout
    except OSError as e:
        return 1, str(e)
"""
_DECODE_MAPPING = """
import subprocess
def run(cmd):
    r = subprocess.run(cmd, capture_output=True)
    return r.stdout.decode("utf-8", errors="replace")
"""
_PLAIN_PROBE = """
import subprocess
def probe(cmd):
    try:
        return subprocess.run(cmd, capture_output=True).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
"""
_MAPPING_WITHOUT_A_RUN = """
def run(cmd):
    try:
        return call(cmd)
    except OSError:
        return {"status": "error"}
"""
_NESTED_RUN_ONLY = """
import subprocess
def outer():
    def inner():
        return subprocess.run(["x"]).returncode
    try:
        return inner()
    except OSError:
        return {"status": "error"}
"""


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a dict mapping around subprocess.run", _DICT_MAPPING, {"run"}),
        ("a tuple mapping around subprocess.run", _TUPLE_MAPPING, {"run"}),
        ("a decode with errors=", _DECODE_MAPPING, {"run"}),
        ("a bool probe", _PLAIN_PROBE, set()),
        ("a mapping with no subprocess.run", _MAPPING_WITHOUT_A_RUN, set()),
        ("a run in a nested function, mapping in the outer", _NESTED_RUN_ONLY, set()),
    ],
)
def test_the_matcher_tells_a_result_mapping_from_a_plain_call(label: str, source: str, expected: set[str]) -> None:
    assert _mapping_functions(source) == expected, label


def test_the_matcher_does_not_flag_the_canonical_sync_runner() -> None:
    """The runner itself calls subprocess.run and returns helper results, never its own literal."""
    source = (repo_root() / _CANONICAL).read_text(encoding="utf-8")
    assert "execute_command_sync" in source, "precondition: the canonical sync runner exists"
    assert _mapping_functions(source) == set()


def test_the_scan_is_not_vacuous() -> None:
    """The nine known sites span seven files; a scan that parses far fewer is blind."""
    _, parsed = _sites()
    assert parsed >= 30, f"parsed {parsed} files mentioning subprocess.run"


def test_no_new_hand_rolled_result_mapping() -> None:
    found, _ = _sites()
    new = {
        rel: sorted(names - _KNOWN.get(rel, frozenset()))
        for rel, names in found.items()
        if names - _KNOWN.get(rel, frozenset())
    }
    assert not new, (
        f"#18180: {new} map a subprocess.run outcome into their own dict/tuple/CommandResult. "
        f"Call `execute_command_sync` from {_CANONICAL} and read its CommandResult instead."
    )


def test_every_known_site_still_maps_its_own_result() -> None:
    """The baseline only drops: a migrated site must delete its entry, or it would hide a regression."""
    found, _ = _sites()
    stale = {
        rel: sorted(names - found.get(rel, frozenset()))
        for rel, names in _KNOWN.items()
        if names - found.get(rel, frozenset())
    }
    assert not stale, f"#18180: {stale} no longer hand-roll a result mapping; delete them from _KNOWN."
