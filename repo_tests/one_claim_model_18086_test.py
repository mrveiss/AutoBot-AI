# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One Claim model (#18086).

Three same-named dataclasses once described one concept (a statement made by an agent or
extracted from a response, compared against the knowledge base): the classifier's, GroundedAgent's
and the conflict resolver's. They are merged into the single `Claim` in
`autobot-backend/services/knowledge_grounding_models.py`; its fields are the union of the three.

The marker is a `class Claim` statement in non-test Python source. The detector reads the syntax
tree, so a docstring or comment that names the class is not a definition, and it matches the exact
name only: `VerifiedClaim` and `ResolvedClaim` are different concepts that wrap a Claim.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot-backend/services/knowledge_grounding_models.py"
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_NAME = "Claim"


def _defines_claim(source: str) -> bool:
    """True when `source` has a `class Claim` statement at any nesting depth."""
    return any(isinstance(n, ast.ClassDef) and n.name == _NAME for n in ast.walk(ast.parse(source)))


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "one-claim-model-scan",
    discover=_source_population,
    # Mid-window, from REACH.window(): (2696, 2996, 2846).
    floor=2846,
    what="non-test python source",
    roots=_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _definers() -> tuple[tuple[str, ...], int]:
    """Files defining `class Claim`, and how many files were parsed."""
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if f"class {_NAME}" not in source:
            continue
        parsed += 1
        if _defines_claim(source):
            found.append(rel)
    return tuple(found), parsed


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a dataclass Claim", "@dataclass\nclass Claim:\n    claim_text: str\n", True),
        ("a pydantic Claim", "class Claim(BaseModel):\n    text: str\n", True),
        ("a nested Claim", "class Outer:\n    class Claim:\n        pass\n", True),
        ("a wrapper of a Claim", "class VerifiedClaim:\n    claim: Claim\n", False),
        ("a resolved wrapper", "class ResolvedClaim:\n    pass\n", False),
        ("a docstring naming it", '"""class Claim: a note"""\nx = 1\n', False),
        ("a use, not a definition", "c = Claim(claim_text='x')\n", False),
    ],
)
def test_the_matcher_tells_a_definition_from_a_use(label: str, source: str, expected: bool) -> None:
    assert _defines_claim(source) is expected, label


def test_the_scan_is_not_vacuous() -> None:
    """The canonical file mentions `class Claim`; zero parsed files is a blind scan."""
    _, parsed = _definers()
    assert parsed >= 1, f"parsed {parsed} files mentioning `class {_NAME}`"


def test_one_claim_model_exists() -> None:
    definers, _ = _definers()
    assert definers == (_CANONICAL,), (
        f"#18086: {list(definers)} define `class {_NAME}`; the one model lives in {_CANONICAL}. "
        "Add the field you need there instead of declaring a second Claim."
    )
