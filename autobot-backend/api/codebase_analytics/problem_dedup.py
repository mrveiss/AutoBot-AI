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


def _normalise(text: object) -> str:
    return " ".join(str(text or "").split()).lower()


def _location(problem: Dict) -> tuple | None:
    """None when the finding carries no line: two line-less findings are not provably one defect."""
    line = problem.get("line") or problem.get("line_number")
    if not line:
        return None
    problem_type = problem.get("type", "")
    family = _family_of(problem_type)
    subject = family if family else (problem_type, _normalise(problem.get("description")))
    return (problem.get("file_path", ""), subject, line)


def _survivor_key(problem: Dict) -> tuple:
    """Highest severity first, then a stable order so input order never decides."""
    tie = tuple(_normalise(problem.get(f)) for f in _TIE_BREAK_FIELDS)
    return (_rank(problem), tie, repr(sorted(problem.items(), key=str)))


def _canonical(problem: Dict) -> Dict:
    family = _family_of(problem.get("type", ""))
    if family and problem["type"] != family[0]:
        return dict(problem, type=family[0])
    return problem


def dedupe_same_location_problems(problems: List[Dict]) -> List[Dict]:
    """Collapse one defect reported more than once; the survivor does not depend on input order."""
    groups: Dict[object, List[Dict]] = {}
    for index, problem in enumerate(problems):
        location = _location(problem)
        groups.setdefault(location if location else ("unlocated", index), []).append(problem)
    return [_canonical(max(group, key=_survivor_key)) for group in groups.values()]
