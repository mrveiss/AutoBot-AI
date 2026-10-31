# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One Claim, VerifiedClaim, Conflict and ConflictResolution model (#18086).

Claim: three same-named dataclasses once described one concept (a statement made by an agent or
extracted from a response, compared against the knowledge base): the classifier's, GroundedAgent's
and the conflict resolver's. They are merged into the single `Claim` in
`autobot-backend/services/knowledge_grounding_models.py`; its fields are the union of the three.

VerifiedClaim, Conflict and ConflictResolution had the same shape of split (GroundedAgent's vs
ClaimVerifier's / ConflictResolver's) and are merged the same way: VerifiedClaim into
`services/knowledge_grounding_models.py`, Conflict and ConflictResolution into
`api/knowledge_grounding_models.py`. `services/agents/subagent_task.py` also has a dataclass named
`ConflictResolution` (consensus between subagent outputs); it is a different concept, so that name
is checked as an Enum only.

The marker is a class statement of an exact name in non-test Python source. The detector reads the
syntax tree, so a docstring or comment that names the class is not a definition, and it matches
the exact name only: `ResolvedClaim` and `ConflictResolver` are different concepts.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: name -> (the one file that may define it, kind). ``kind`` separates a class from the
#: unrelated same-name classes: `ConflictResolution` is also a dataclass in
#: `services/agents/subagent_task.py` (consensus between subagent outputs), a different concept.
_ONE_MODEL = {
    "Claim": ("autobot-backend/services/knowledge_grounding_models.py", "any"),
    "VerifiedClaim": ("autobot-backend/services/knowledge_grounding_models.py", "any"),
    "Conflict": ("autobot-backend/api/knowledge_grounding_models.py", "any"),
    "ConflictResolution": ("autobot-backend/api/knowledge_grounding_models.py", "enum"),
}
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")


def _is_enum(node: ast.ClassDef) -> bool:
    return any(isinstance(b, ast.Name) and b.id == "Enum" for b in node.bases)


def _defined_names(source: str) -> set[str]:
    """Names in `_ONE_MODEL` that `source` defines as a class, at any nesting depth."""
    found = set()
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.ClassDef) and n.name in _ONE_MODEL:
            if _ONE_MODEL[n.name][1] == "any" or _is_enum(n):
                found.add(n.name)
    return found


def _defines_claim(source: str) -> bool:
    """Back-compat for the matcher cases: True when `class Claim` is defined."""
    return "Claim" in _defined_names(source)


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
    floor=3221,  # re-pinned mid-window (train 73): population 3250, window [2950, 3250] (#17844)
    what="non-test python source",
    roots=_ROOTS,
    growth=300,
)


_MENTIONS = tuple(f"class {n}" for n in _ONE_MODEL)


@functools.lru_cache(maxsize=1)
def _definers() -> tuple[dict[str, tuple[str, ...]], int]:
    """name -> files defining it, and how many files were parsed."""
    found: dict[str, list[str]] = {n: [] for n in _ONE_MODEL}
    parsed = 0
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if not any(m in source for m in _MENTIONS):
            continue
        parsed += 1
        for name in _defined_names(source):
            found[name].append(rel)
    return {n: tuple(v) for n, v in found.items()}, parsed


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


def test_the_matcher_covers_every_merged_name_and_tells_an_enum_from_a_dataclass() -> None:
    assert _defined_names("class Conflict:\n    pass\n") == {"Conflict"}
    assert _defined_names("@dataclass\nclass VerifiedClaim:\n    pass\n") == {"VerifiedClaim"}
    assert _defined_names("class ConflictResolution(str, Enum):\n    A = 'a'\n") == {"ConflictResolution"}
    # The unrelated subagent dataclass of the same name is not the enum.
    assert _defined_names("@dataclass\nclass ConflictResolution:\n    task_ids: list\n") == set()
    assert _defined_names("class ConflictResolver:\n    pass\n") == set()


def test_the_scan_is_not_vacuous() -> None:
    """Every canonical file defines its names; a name nobody defines means a blind scan."""
    found, parsed = _definers()
    assert parsed >= 2, f"parsed {parsed} files mentioning a merged class"
    assert all(found[n] for n in _ONE_MODEL), {n: v for n, v in found.items() if not v}


@pytest.mark.parametrize("name", sorted(_ONE_MODEL))
def test_one_model_exists(name: str) -> None:
    found, _ = _definers()
    canonical = _ONE_MODEL[name][0]
    assert found[name] == (canonical,), (
        f"#18086: {list(found[name])} define `class {name}`; the one model lives in {canonical}. "
        "Add the field you need there instead of declaring a second one."
    )
