# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One defect at one location counts once (#20493).

Two detectors can describe the same defect under different type names: the AST
pass reports ``long_function`` for every function over the line limit, and the
anti-pattern pass reports ``code_smell_long_method`` for the same class methods.
Stored side by side they double the count. The canonical type is kept (it is the
one the code-smell panel recognises) and takes the highest severity of the group.
"""

from typing import Dict, List

from autobot_shared.status_enums import Severity

#: Each tuple is one defect described by several types; the first is canonical.
SAME_DEFECT_FAMILIES = (("long_function", "code_smell_long_method"),)


def _rank(problem: Dict) -> int:
    return Severity.rank_of(str(problem.get("severity", "")), default=0)


def _family_of(problem_type: str) -> tuple:
    """The family a type belongs to; a type in no family is its own family."""
    for family in SAME_DEFECT_FAMILIES:
        if problem_type in family:
            return family
    return (problem_type,)


def _location(problem: Dict, family: tuple) -> tuple | None:
    """None when the finding carries no line: two line-less findings are not provably one defect."""
    line = problem.get("line") or problem.get("line_number")
    return (problem.get("file_path", ""), family, line) if line else None


def dedupe_same_location_problems(problems: List[Dict]) -> List[Dict]:
    """Collapse one defect reported more than once at one line of one file.

    Applies to every type, not one named pair: the same type twice at one line
    (two passes over the same construct) and the members of a
    ``SAME_DEFECT_FAMILIES`` entry both collapse to a single finding that keeps
    the highest severity. Works on one file's list (write path) and on a
    multi-file list (read path), because the file path is part of the key.
    """
    kept: List[Dict] = []
    by_location: Dict[tuple, Dict] = {}
    for problem in problems:
        family = _family_of(problem.get("type", ""))
        location = _location(problem, family)
        first = by_location.get(location) if location else None
        if first is None:
            canonical = dict(problem, type=family[0])
            if location:
                by_location[location] = canonical
            kept.append(canonical)
        elif _rank(problem) > _rank(first):
            first["severity"] = problem["severity"]
    return kept
