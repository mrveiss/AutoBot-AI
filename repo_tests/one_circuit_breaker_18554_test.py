# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new hand-rolled circuit breaker; the generic one lives in autobot_shared (#18554).

`autobot_shared/circuit_breaker.py` is the one generic breaker (call wrapper, manager
registry, decorators). A class that re-implements it -- a failure threshold plus a recovery
timeout -- or a second CLOSED/OPEN/HALF_OPEN enum is a fork: states never compare equal across
enum classes (#12656) and thresholds drift.

WHAT MATCHES (syntax tree only, so a comment or string naming these is not a site)
    CLASS  a class whose own body (not a nested class) uses, as a name, attribute or parameter,
           both a failure-threshold/count identifier and a recovery/cooldown-timeout one.
    ENUM   an `Enum` subclass assigning CLOSED, OPEN and HALF_OPEN members.
BOUNDARY
    Scanned: tracked non-test `.py` under `SCAN_ROOTS`. Exempt by path: the canonical module.
    NOT seen: module-global breakers with no class (the Jina Reader one, B9), state held in dicts
    or string keys, and breakers whose identifiers avoid these words. Those are separate findings.

THE ALLOWLIST (`hand_rolled_circuit_breaker_baseline_18554.py`) freezes today's legitimate
matches with a reason each. It may only shrink: a new match fails, a stale entry fails.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.hand_rolled_circuit_breaker_baseline_18554 import ALLOWLIST, FROZEN_TOTAL

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

CANONICAL = "autobot_shared/circuit_breaker.py"
SCAN_ROOTS = (
    "autobot-backend",
    "autobot-slm-backend",
    "autobot_shared",
    "autobot-npu-worker",
    "autobot-tts-worker",
    "autobot-browser-worker",
    "plugins",
    "libs",
)
_FAILURE = re.compile(
    r"fail\w*threshold|threshold\w*fail|max_?failures|fail(ure)?s?_?(count|limit)|fail_max|"
    r"error_threshold|consecutive_fail|breaker\w*threshold"
)
_COOLDOWN = re.compile(
    r"recovery_?(timeout|time|seconds|period)|cool_?down|reset_timeout|open_(timeout|duration|until|seconds)|"
    r"half_open_timeout|retry_after|breaker\w*timeout"
)
_STATES = frozenset({"closed", "open", "half_open"})


def _is_scanned(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if not rel.endswith(".py") or rel == CANONICAL:
        return False
    return not (name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py" or "/tests/" in rel)


def _identifiers(cls: ast.ClassDef) -> set[str]:
    """Lower-cased names, attributes and parameters in the class body, nested classes excluded."""
    found: set[str] = set()
    stack: list[ast.AST] = list(cls.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.ClassDef):
            continue
        stack.extend(ast.iter_child_nodes(node))
        if isinstance(node, ast.Name):
            found.add(node.id.lower())
        elif isinstance(node, ast.Attribute):
            found.add(node.attr.lower())
        elif isinstance(node, ast.arg):
            found.add(node.arg.lower())
    return found


def _is_state_enum(cls: ast.ClassDef) -> bool:
    if not any(ast.unparse(base).endswith("Enum") for base in cls.bases):
        return False
    members = {
        t.id.lower() for n in cls.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)
    }
    return _STATES <= members


def breaker_shapes(source: str) -> list[tuple[str, str]]:
    """`(class name, kind)` for every breaker-shaped class in `source`."""
    shapes: list[tuple[str, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ClassDef):
            continue
        if _is_state_enum(node):
            shapes.append((node.name, "ENUM"))
        names = _identifiers(node)
        if any(_FAILURE.search(n) for n in names) and any(_COOLDOWN.search(n) for n in names):
            shapes.append((node.name, "CLASS"))
    return shapes


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *SCAN_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_scanned(rel)]


REACH = declare(
    "hand-rolled-circuit-breaker-scan",
    discover=_population,
    # Mid-window, from REACH.window(): population 3209 at eabcae7394 -> (2909, 3209, 3059).
    floor=3305,  # re-pinned mid-window (train 82 on main)
    what="non-test python source",
    roots=SCAN_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _found() -> frozenset[str]:
    keys: set[str] = set()
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        keys.update(f"{rel}::{name}::{kind}" for name, kind in breaker_shapes(source))
    return frozenset(keys)


_HAND_ROLLED = """
class MyBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
"""
_CONSTANTS = """
class Limits:
    MAX_FAILURES = 3
    COOLDOWN_SECONDS = 30
"""
_OWN_ENUM = """
import enum
class State(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
"""


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("threshold plus recovery timeout", _HAND_ROLLED, [("MyBreaker", "CLASS")]),
        ("class-level constants", _CONSTANTS, [("Limits", "CLASS")]),
        ("a second state enum", _OWN_ENUM, [("State", "ENUM")]),
        (
            "threshold only",
            "class Retry:\n    def __init__(self, failure_threshold=3):\n        self.n = failure_threshold\n",
            [],
        ),
        (
            "timeout only",
            "class Cache:\n    def __init__(self, recovery_timeout=3):\n        self.t = recovery_timeout\n",
            [],
        ),
        ("an unrelated enum", "from enum import Enum\nclass E(Enum):\n    OPEN = 1\n    CLOSED = 2\n", []),
        (
            "a plain class using the canonical breaker",
            "class Svc:\n    def go(self):\n        return CircuitBreaker('x')\n",
            [],
        ),
        (
            "only comments and strings naming it",
            '# failure_threshold recovery_timeout\nclass A:\n    """failure_threshold recovery_timeout"""\n',
            [],
        ),
        (
            "a nested class does not leak to its parent",
            "class Outer:\n    class Inner:\n        failure_threshold = 1\n        recovery_timeout = 1\n",
            [("Inner", "CLASS")],
        ),
    ],
)
def test_the_detector_tells_a_breaker_from_a_lookalike(
    label: str, source: str, expected: list[tuple[str, str]]
) -> None:
    assert breaker_shapes(source) == expected, label


def test_the_canonical_module_is_exempt_and_nothing_else_is() -> None:
    assert not _is_scanned(CANONICAL)
    assert _is_scanned("autobot-backend/circuit_breaker.py")
    assert not _is_scanned("autobot-backend/circuit_breaker_test.py")
    assert not _is_scanned("autobot-backend/tests/resilience/test_circuit_breaker.py")


def test_the_scan_is_not_vacuous() -> None:
    """The scan must see the known fixtures: a blind scan reports an empty, clean tree."""
    found = _found()
    assert len(found) >= 10, f"only {len(found)} breaker-shaped classes found; the scan stopped reaching the tree"
    assert any(k.endswith("::CircuitState::ENUM") for k in found)


def test_no_new_hand_rolled_circuit_breaker() -> None:
    new = sorted(_found() - set(ALLOWLIST))
    assert not new, (
        f"#18554: {new} look like a hand-rolled circuit breaker (failure threshold + recovery timeout, or a "
        f"CLOSED/OPEN/HALF_OPEN enum). Use {CANONICAL} (CircuitBreaker / get_circuit_breaker_manager / "
        "CircuitState). If it is genuinely per-entity routing state, add it to the allowlist with a reason."
    )


def test_every_allowlist_entry_still_matches() -> None:
    stale = sorted(set(ALLOWLIST) - _found())
    assert not stale, f"stale allowlist entries (class gone or no longer matching); delete these lines: {stale}"


def test_the_allowlist_only_shrinks_and_every_entry_has_a_reason() -> None:
    assert len(ALLOWLIST) <= FROZEN_TOTAL, f"{len(ALLOWLIST)} entries exceeds the frozen {FROZEN_TOTAL}"
    assert all(reason.strip() for reason in ALLOWLIST.values())
