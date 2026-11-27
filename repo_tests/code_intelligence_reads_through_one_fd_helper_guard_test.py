# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No code-intelligence module re-opens a discovered path by name (#21289).

``discover_files`` walks by directory descriptor, but a detector that then calls ``open(path)`` /
``Path.read_text()`` on the discovered path re-resolves every component by name, so a directory swapped
for an out-of-root symlink between discovery and read is followed (TOCTOU, THREAT_MODEL.md section 1).
Every source read goes through ``code_intelligence.python_files.read_source_text``.

A read-mode ``open()``, ``.open()``, ``.read_text()`` or ``.read_bytes()`` call in a non-test module of
``autobot-backend/code_intelligence`` fails unless its enclosing function (qualified name) is in
``_NOT_DISCOVERED_READS`` for that module, with the reason its path is never a discovered one: a NEW
by-name read in an allowlisted module fails too. A stale allowlist entry fails as well.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Tuple

from repo_tests._paths import repo_root

from autobot_shared.testfile_names import is_test_filename

_PKG = repo_root() / "autobot-backend" / "code_intelligence"
_HELPER = "read_source_text"
_READ_ATTRS = {"read_text", "read_bytes", "open"}
_WRITE_MODES = ("w", "a", "x", "+")

# (module, qualified function) allowed a by-name read, each with why the path is not one ``discover_files`` produced.
_NOT_DISCOVERED_READS: Dict[Tuple[str, str], str] = {
    ("python_files.py", "read_source_text"): "the helper's own fallback for a path no discovery covered",
    ("log_pattern_miner.py", "LogPatternMiner.parse_file"): "reads log files named by the caller, not discovered source",
}

# Measured at this head: 97 non-test modules scanned, 26 ``read_source_text`` call sites.
# An extractor that stops matching reads clean at zero; lower these only when the tree holds fewer.
_MODULE_FLOOR = 97
_HELPER_CALL_FLOOR = 26


def _modules() -> List[Path]:
    return [p for p in sorted(_PKG.rglob("*.py")) if "test" not in p.parts and not is_test_filename(p.name)]


def _is_write(call: ast.Call) -> bool:
    for arg in [*call.args[1:2], *(k.value for k in call.keywords if k.arg == "mode")]:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return any(m in arg.value for m in _WRITE_MODES)
    return False


def _is_read_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "open" and not _is_write(node)
    return isinstance(func, ast.Attribute) and func.attr in _READ_ATTRS and not _is_write(node)


def _walk(node: ast.AST, scope: Tuple[str, ...]):
    """Yield ``(node, qualified enclosing function/class name)`` for every node below *node*."""
    for child in ast.iter_child_nodes(node):
        named = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        inner = scope + (child.name,) if named else scope
        yield child, ".".join(inner)
        yield from _walk(child, inner)


def _scan() -> tuple[Dict[Tuple[str, str], List[int]], int]:
    reads: Dict[Tuple[str, str], List[int]] = {}
    helper_calls = 0
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(_PKG).as_posix()
        for node, qualname in _walk(tree, ()):
            if _is_read_call(node):
                reads.setdefault((rel, qualname), []).append(node.lineno)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == _HELPER:
                helper_calls += 1
    return reads, helper_calls


def test_sweep_sees_the_tree():
    reads, helper_calls = _scan()
    assert len(_modules()) >= _MODULE_FLOOR, "FIX THE SWEEP: module glob found too little"
    assert helper_calls >= _HELPER_CALL_FLOOR, f"FIX THE SWEEP: {helper_calls} calls, floor {_HELPER_CALL_FLOOR}"
    assert reads, "FIX THE SWEEP: no read call matched anywhere; the allowlisted modules alone must match"


def test_no_module_reopens_a_path_by_name():
    reads, _ = _scan()
    offenders = {key: lines for key, lines in reads.items() if key not in _NOT_DISCOVERED_READS}
    assert not offenders, f"read through python_files.{_HELPER}, not by name: {offenders}"


def test_allowlist_has_no_stale_entries():
    reads, _ = _scan()
    stale = sorted(key for key in _NOT_DISCOVERED_READS if key not in reads)
    assert not stale, f"allowlisted functions with no by-name read left: {stale}"
