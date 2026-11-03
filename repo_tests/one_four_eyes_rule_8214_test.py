#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One four-eyes rule (#8214): its home is ``autobot_shared/approval_four_eyes.py``.

Three copies had grown and two of them compared a count, which let a requester who was not
eligible pass when someone else was the sole admin. This pins the shape by BEHAVIOUR, not by
name: code that compares a decider with a requester, or parses ``requested_by_agent``, is a
second implementation whatever it is called. Callers pass their eligible set to the home.

Reach: the sweep binds to ``check_symbol_forks``' declared floor, so an enumeration that
collapses fails here instead of reading as clean.
"""

from __future__ import annotations

import ast
import sys

from repo_tests._paths import repo_root

sys.path.insert(0, str(repo_root() / "tools" / "lint"))
import check_symbol_forks as detector  # noqa: E402

HOME = "autobot_shared/approval_four_eyes.py"
SINGLE_DEFINITIONS = ("FourEyesError", "four_eyes_self_approval")


def _names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def _reads_requested_by(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Attribute) and n.attr == "requested_by_agent" for n in ast.walk(node))


def _copies_the_rule(tree: ast.Module) -> list[int]:
    """Lines comparing a decider with a requester, or splitting ``requested_by_agent``."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and {"decider", "requester"} <= _names(node):
            found.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("split", "rsplit", "partition", "rpartition") and _reads_requested_by(node):
                found.append(node.lineno)
    return found


def _sweep() -> tuple[dict[str, list[int]], int]:
    """Offenders by file over the detector's population, and how many files were parsed."""
    offenders: dict[str, list[int]] = {}
    parsed = 0
    for path in detector.fork_scan_files():
        rel = path.as_posix()
        if not detector.in_population(path) or rel == HOME:
            continue
        try:
            tree = ast.parse((repo_root() / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue
        parsed += 1
        lines = _copies_the_rule(tree)
        if lines:
            offenders[rel] = lines
    return offenders, parsed


def test_no_second_four_eyes_rule_by_behaviour() -> None:
    offenders, parsed = _sweep()
    assert parsed >= detector.MIN_FILES_PARSED, (
        f"the sweep parsed {parsed} files, under the detector's floor of {detector.MIN_FILES_PARSED} — "
        "an enumeration that collapsed must not read as a clean tree"
    )
    assert not offenders, f"#8214: {offenders} re-implement the four-eyes rule; pass the eligible set to {HOME}"


def test_the_detector_sees_each_shape_it_claims_to() -> None:
    """A zero means nothing unless these controls are found."""
    assert _copies_the_rule(ast.parse("x = decider != requester"))
    assert _copies_the_rule(ast.parse("if requester == decider and n >= 2: pass"))
    assert _copies_the_rule(ast.parse('i = str(a.requested_by_agent).rsplit(":", 1)[-1]'))
    assert not _copies_the_rule(ast.parse("x = decider != owner"))


def test_the_rule_and_its_error_have_one_definition() -> None:
    clusters = detector.find_clusters(detector.fork_scan_files())[0]
    for name in SINGLE_DEFINITIONS:
        cluster = clusters.get(name)
        homes = sorted(d.path for d in cluster.definitions) if cluster else []
        assert not homes, f"#8214: {name} is defined in {homes}; its one home is {HOME}"
