# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One defect at one location counts once (#20493).

Two detectors can describe the same defect under different type names: the AST
pass reports ``long_function`` for every function over the line limit, and the
anti-pattern pass reports ``code_smell_long_method`` for the same class methods.
Stored side by side they double the count. Types listed together in
``SAME_DEFECT_FAMILIES`` merge across type at one line; every other type merges
only with an identical finding (same type, line and normalised description), so
two different defects on one line both stay.

A line number is compared as a number (``5`` and ``"5"`` are one line, #21782), the
description keeps its case (``Cache`` and ``cache`` are two identifiers), and a
finding with no ``file_path`` is never merged with another in a read across files.
"""

from typing import Dict, List

from autobot_shared.status_enums import Severity

#: Each tuple is one defect described by several types; the first is canonical.
SAME_DEFECT_FAMILIES = (("long_function", "code_smell_long_method"),)

_TIE_BREAK_FIELDS = ("description", "suggestion")


def _rank(problem: Dict) -> int:
    return Severity.rank_of(str(problem.get("severity", "")), default=0)


def _family_of(problem_type: str) -> tuple | None:
    for family in SAME_DEFECT_FAMILIES:
        if problem_type in family:
            return family
    return None


def _squash(text: object) -> str:
    """Whitespace collapsed, case kept: identifiers that differ only in case are different."""
    return " ".join(str(text or "").split())


def _normalise(text: object) -> str:
    return _squash(text).lower()


def normalise_line(value: object) -> int | None:
    """A line number as an int; ``None`` when absent, zero or not a number (#21782)."""
    try:
        return int(value) or None  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


def _location(problem: Dict, within_file: bool) -> tuple | None:
    """None when the finding is not provably one defect: no line, or (across files) no file."""
    line = normalise_line(problem.get("line") or problem.get("line_number"))
    path = problem.get("file_path", "")
    if not line or not (path or within_file):
        return None
    problem_type = problem.get("type", "")
    family = _family_of(problem_type)
    subject = family if family else (problem_type, _squash(problem.get("description")))
    return (path, subject, line)


def _survivor_key(problem: Dict) -> tuple:
    """Highest severity first, then a stable order so input order never decides."""
    tie = tuple(_normalise(problem.get(f)) for f in _TIE_BREAK_FIELDS)
    return (_rank(problem), tie, repr(sorted(problem.items(), key=str)))


def _canonical(problem: Dict) -> Dict:
    family = _family_of(problem.get("type", ""))
    if family and problem["type"] != family[0]:
        return dict(problem, type=family[0])
    return problem


def dedupe_same_location_problems(problems: List[Dict], within_file: bool = False) -> List[Dict]:
    """Collapse one defect reported more than once; the survivor does not depend on input order.

    ``within_file`` is for the list of ONE file, whose findings carry no ``file_path`` yet.
    """
    groups: Dict[object, List[Dict]] = {}
    for index, problem in enumerate(problems):
        location = _location(problem, within_file)
        groups.setdefault(location if location else ("unlocated", index), []).append(problem)
    return [_canonical(max(group, key=_survivor_key)) for group in groups.values()]
