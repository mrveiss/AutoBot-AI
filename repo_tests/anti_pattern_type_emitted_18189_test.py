# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every `AntiPatternType` member has an emitter (#18189).

Owner decision 2026-10-10: the enum declares only smells a detector emits. Five members
(primitive obsession, shotgun surgery, inappropriate intimacy, speculative generality,
refused bequest) were declared but never produced, and the `/types` catalog advertised them
as "no detector currently emits this type". They were removed; each returns when a detector
ships.

The marker is a keyword argument `pattern_type=AntiPatternType.<NAME>` -- a result being
constructed. A catalog dict key, a comparison, or the enum's own definition is not an
emitter. The detector reads the syntax tree, so prose naming a member is not one either.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ENUM = "AntiPatternType"


def _emitted_members(source: str) -> set[str]:
    """Members used as `pattern_type=AntiPatternType.<NAME>` in a call."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            v = kw.value
            if (
                kw.arg == "pattern_type"
                and isinstance(v, ast.Attribute)
                and isinstance(v.value, ast.Name)
                and v.value.id == _ENUM
            ):
                found.add(v.attr)
    return found


def _unemitted(declared: set[str], sources: list[str]) -> set[str]:
    emitted: set[str] = set()
    for src in sources:
        emitted |= _emitted_members(src)
    return declared - emitted


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend/code_analysis", "autobot-backend/code_intelligence")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "anti-pattern-type-emitters",
    discover=_source_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=125,
    what="non-test python source in the two detector packages",
    roots=("autobot-backend/code_analysis", "autobot-backend/code_intelligence"),
    growth=30,
)


@functools.lru_cache(maxsize=1)
def _population_sources() -> tuple[str, ...]:
    return tuple((repo_root() / rel).read_text(encoding="utf-8") for rel in REACH.examined(repo_root()))


def _declared_members() -> set[str]:
    from code_analysis.src.anti_pattern_detector import AntiPatternType

    return {m.name for m in AntiPatternType}


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a result construction", "X(pattern_type=AntiPatternType.GOD_CLASS)\n", {"GOD_CLASS"}),
        (
            "a catalog dict key",
            "D = {" + "AntiPatternType.GOD_CLASS: 1}\n",
            set(),
        ),  # split: one literal would read as a format field
        ("a comparison", "if t == AntiPatternType.GOD_CLASS:\n    pass\n", set()),
        ("a comment", "# pattern_type=AntiPatternType.GOD_CLASS\n", set()),
        ("the sibling test enum", "X(pattern_type=TestAntiPatternType.GOD_CLASS)\n", set()),
    ],
)
def test_the_matcher_tells_an_emitter_from_a_mention(label: str, source: str, expected: set[str]) -> None:
    assert _emitted_members(source) == expected, label


def test_a_new_unemitted_member_is_reported() -> None:
    emits = "X(pattern_type=AntiPatternType.GOD_CLASS)\n"
    assert _unemitted({"GOD_CLASS"}, [emits]) == set()
    assert _unemitted({"GOD_CLASS", "SHOTGUN_SURGERY"}, [emits]) == {"SHOTGUN_SURGERY"}


def test_the_scan_is_not_vacuous() -> None:
    assert len(_population_sources()) >= 10


def test_every_antipatterntype_member_has_an_emitter() -> None:
    missing = _unemitted(_declared_members(), list(_population_sources()))
    assert not missing, (
        f"#18189: {sorted(missing)} are declared in AntiPatternType but no detector constructs a result "
        "with them. Ship the detector in the same change that adds the member."
    )
