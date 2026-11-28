# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One seam for "an LLM scores quality" (#16133).

The RLM evaluator and the judges family each called `complete_validated` and unwrapped the
reply with their own copy of the same line. Both now go through
`llm_shared.quality_judgment.judge_validated`. The prompts, schemas, scales and thresholds
stay each caller's own: they answer different questions (see that module).

The marker is a *call* to `complete_validated` inside the two judging packages. The detector
reads the syntax tree, so an import or prose naming it is not a fork.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend/judges", "autobot-backend/rlm", "autobot-backend/agent_loop")
_SEAM_CALLERS = (
    "autobot-backend/judges/__init__.py",
    "autobot-backend/rlm/evaluator.py",
    "autobot-backend/agent_loop/think_tool.py",
)


def _calls(source: str, name: str) -> bool:
    """True when `source` calls `name(...)` or `<x>.name(...)`."""
    for node in ast.walk(parse_cache.parse(source)):
        if isinstance(node, ast.Call):
            fn = node.func
            if (isinstance(fn, ast.Name) and fn.id == name) or (isinstance(fn, ast.Attribute) and fn.attr == name):
                return True
    return False


def _is_source_python(rel: str) -> bool:
    return rel.endswith(".py") and not (
        is_test_filename(rel, include_js=False, include_conftest=False) or "/tests/" in rel
    )


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "llm-quality-seam-scan",
    discover=_population,
    # Mid-window, from REACH.window(); arithmetic on the commit.
    floor=34,
    what="non-test judging python",
    roots=_ROOTS,
    growth=4,
)


@functools.lru_cache(maxsize=1)
def _forks() -> tuple[str, ...]:
    return tuple(
        rel
        for rel in REACH.examined(repo_root())
        if _calls((repo_root() / rel).read_text(encoding="utf-8"), "complete_validated")
    )


# Contrast pair: the fork shape is caught, the seam shape is not.
_FORK = (
    "async def f():\n    p = await complete_validated('', 'p', S, completer=c, label='x')\n    return p.model_dump()\n"
)
_SEAM = "async def f():\n    return await judge_validated('', 'p', S, completer=c, label='x')\n"
_MENTION = "from llm_shared.validated_llm import complete_validated\n# complete_validated(x)\n"


@pytest.mark.parametrize(
    ("source", "expected"),
    [(_FORK, True), (_SEAM, False), (_MENTION, False), ("x = module.complete_validated(1)\n", True)],
)
def test_the_matcher_tells_the_fork_from_the_seam(source: str, expected: bool) -> None:
    assert _calls(source, "complete_validated") is expected


def test_no_judging_module_calls_complete_validated_directly() -> None:
    assert _forks() == (), (
        f"#16133: {list(_forks())} call complete_validated; an LLM quality judgment goes through "
        "llm_shared.quality_judgment.judge_validated."
    )


@pytest.mark.parametrize("rel", _SEAM_CALLERS)
def test_each_judging_family_uses_the_seam(rel: str) -> None:
    assert _calls((repo_root() / rel).read_text(encoding="utf-8"), "judge_validated"), rel
