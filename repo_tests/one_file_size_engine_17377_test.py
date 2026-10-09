# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One file-size ratchet engine, and every size gate a configuration of it (#17377).

The Python, shell and frontend size gates each carried their own copy of the ratchet --
the enumeration, the line count, the three-way verdict, the reach floor -- and #17885
added the third copy two weeks after #17377 was filed to remove the second. A shared
engine with no guard is a suggestion; this guard makes it the only way to write a gate.

## What "re-implements" means here

A gate may hold DATA (its limit, ceilings, prefixes, floor, paths) and DELEGATIONS to
``tools.lint.file_size_engine``. It may not hold the LOGIC, which shows up as one of:

* a comparison against the limit or a ceiling (``line_count > MAX_LINES``) -- the verdict;
* opening a file or spawning ``git`` -- the measurement and the enumeration;
* a ratchet finding's wording outside a docstring -- the report.

## Why an AST check and not a grep

Every gate's docstring explains the ratchet in prose, including the words a text scan
would key on. The detector reads call, compare and string nodes and skips docstrings, so
a gate describing the rule is not a gate implementing it.
"""

from __future__ import annotations

import ast
import re

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()

#: The engine every gate must import, as a dotted module name (not a file literal).
_ENGINE = "tools.lint.file_size_engine"

#: A size gate is ``scripts/check_<language>_file_size.py``. Matched by name over the
#: tracked ``scripts`` tree, so a fourth gate is discovered, not remembered.
_GATE_NAME = re.compile(r"^scripts/check_[a-z]+_file_size\.py$")

#: The three gates that exist today. A floor, not the population: the discovery above
#: must find at least these, or it has stopped looking.
_KNOWN_GATES = {
    "scripts/check_python_file_size.py",
    "scripts/check_shell_file_size.py",
    "scripts/check_frontend_file_size.py",
}

#: Names whose comparison IS the verdict.
_LIMIT_NAMES = frozenset({"MAX_LINES", "max_lines", "ceiling", "line_count"})

#: Fragments of the ratchet's findings. Owned by the engine; a gate repeating one is a fork
#: of the report, which `gate_reporting_parity_17377_test.py` would otherwise have to chase.
_FINDING_FRAGMENTS = (
    "over its recorded ceiling",
    "under its recorded ceiling",
    "could not be read, so its size was never measured",
    "not found by the tracked-file walk",
)


def _docstring_ids(tree: ast.AST) -> set[int]:
    """``id()`` of every docstring node, so prose about the ratchet is not read as code."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _imports_engine(tree: ast.AST) -> bool:
    """Whether *tree* imports the engine, in any of the three spellings."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "tools.lint":
            if any(alias.name == "file_size_engine" for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module == _ENGINE:
            return True
        if isinstance(node, ast.Import) and any(alias.name == _ENGINE for alias in node.names):
            return True
    return False


def _name_of(node: ast.AST) -> str | None:
    """The bare or attribute name *node* refers to, if it is one."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _node_finding(node: ast.AST, docstrings: set[int]) -> str | None:
    """A reason *node* is ratchet logic, or None."""
    if isinstance(node, ast.Compare):
        names = {_name_of(n) for n in (node.left, *node.comparators)}
        if names & _LIMIT_NAMES:
            return f"line {node.lineno}: compares against the limit or a ceiling (the verdict)"
    if isinstance(node, ast.Call):
        callee = _name_of(node.func)
        owner = _name_of(node.func.value) if isinstance(node.func, ast.Attribute) else None
        if callee == "open" or owner == "subprocess":
            return f"line {node.lineno}: opens a file or spawns a process (the measurement)"
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
        if any(fragment in node.value for fragment in _FINDING_FRAGMENTS):
            return f"line {node.lineno}: spells a ratchet finding (the report)"
    return None


def reimplementations(source: str) -> list[str]:
    """Reasons *source* carries the ratchet itself instead of configuring the engine."""
    tree = ast.parse(source)
    reasons = [] if _imports_engine(tree) else [f"does not import {_ENGINE}"]
    docstrings = _docstring_ids(tree)
    for node in ast.walk(tree):
        finding = _node_finding(node, docstrings)
        if finding is not None:
            reasons.append(finding)
    return reasons


def _gates() -> list[str]:
    """Every tracked size gate, discovered by name under ``scripts``."""
    return sorted(rel for rel in tracked_paths(_ROOT, "scripts") if _GATE_NAME.match(rel))


# --- contrast pair: the detector must tell a configuration from a fork --------------------

_THIN_GATE = '''
"""A gate that is over its recorded ceiling -- in prose only, which is allowed."""
from tools.lint import file_size_engine as engine
MAX_LINES = 600
def _config():
    return engine.GateConfig(label="x", max_lines=MAX_LINES)
def verdict(rel, line_count):
    return engine.verdict(_config(), rel, line_count)
'''

_FORKED_GATE = """
import subprocess
MAX_LINES = 600
def count_lines(path):
    with path.open(encoding="utf-8") as handle:
        return sum(1 for _ in handle)
def verdict(rel, line_count):
    if line_count > MAX_LINES:
        return f"{rel}: {line_count} lines, over its recorded ceiling of 1."
def tracked():
    return subprocess.run(["git", "ls-files"]).stdout
"""


def test_the_detector_passes_a_configuration() -> None:
    assert reimplementations(_THIN_GATE) == []


def test_the_detector_trips_on_a_fork() -> None:
    reasons = " | ".join(reimplementations(_FORKED_GATE))
    for expected in ("does not import", "the verdict", "the measurement", "the report"):
        assert expected in reasons, f"the fork fixture was not flagged for {expected!r}: {reasons}"


# --- the live tree -----------------------------------------------------------------------


def test_discovery_reaches_every_known_gate() -> None:
    """Non-vacuity: an empty discovery passes the parametrised test below by testing nothing."""
    missing = _KNOWN_GATES - set(_gates())
    assert not missing, f"gate discovery under scripts missed {sorted(missing)} -- the pattern or root is wrong"


@pytest.mark.parametrize("rel", _gates())
def test_every_size_gate_is_a_configuration_of_the_engine(rel: str) -> None:
    reasons = reimplementations((_ROOT / rel).read_text(encoding="utf-8"))
    assert not reasons, (
        f"{rel} re-implements the file-size ratchet instead of configuring {_ENGINE}:\n  "
        + "\n  ".join(reasons)
        + "\n\n#17377: three gates carried three copies, and each fix had to land three times. "
        "Put what differs in the gate's GateConfig, and anything else in the engine."
    )
