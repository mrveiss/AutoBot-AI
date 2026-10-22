# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No caller reaches into the semantic chunker's private embedding hooks (#18185).

`SemanticChunkerBase` exposes `load_embedding_model`, `embed_sentences` and
`embed_sentences_sync` for callers that need the chunker's own vectors. The underscore
members behind them (`_initialize_model`, `_compute_embeddings`,
`_compute_sentence_embeddings*`) are hardware hooks that only `utils/semantic_chunker*.py`
may touch. The detector reads the syntax tree: any attribute access of one of those names
on a receiver other than `self`/`cls` -- a call or a bare reference -- is a reach-in.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_PRIVATE = frozenset(
    {"_initialize_model", "_compute_embeddings", "_compute_sentence_embeddings", "_compute_sentence_embeddings_async"}
)
_ROOTS = ("autobot-backend", "autobot-infrastructure", "autobot_shared")
_OWN_DIR = "autobot-backend/utils/"
_OWN_PREFIX = "semantic_chunker"


def _is_chunker_module(rel: str) -> bool:
    """`utils/semantic_chunker*.py` -- the only place allowed to touch the hooks."""
    return rel.startswith(_OWN_DIR) and rel[len(_OWN_DIR) :].startswith(_OWN_PREFIX) and "/" not in rel[len(_OWN_DIR) :]


def _reach_ins(source: str) -> list[str]:
    """Private hook names accessed on a receiver other than self/cls."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr in _PRIVATE:
            if not (isinstance(node.value, ast.Name) and node.value.id in ("self", "cls")):
                found.append(node.attr)
    return found


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if rel.endswith(".py")]


REACH = declare(
    "chunker-private-hook-scan",
    discover=_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=5455,  # re-pinned mid-window (train 69): population 5605, window [5305, 5605] (#17844)
    what="tracked python",
    roots=_ROOTS,
    growth=300,
)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        (
            "async compute on a chunker",
            "await chunker._compute_sentence_embeddings_async(x)\n",
            ["_compute_sentence_embeddings_async"],
        ),
        ("model init on a chunker", "await chunker._initialize_model()\n", ["_initialize_model"]),
        ("a bare reference", "run(chunker._compute_sentence_embeddings, 1)\n", ["_compute_sentence_embeddings"]),
        ("the public API", "await chunker.embed_sentences(x)\nawait chunker.load_embedding_model()\n", []),
        (
            "a class using its own hook",
            "class A:\n    async def f(self):\n        await self._initialize_model()\n",
            [],
        ),
        ("a string naming it", 'patch.object(c, "_initialize_model")\n', []),
    ],
)
def test_the_matcher_tells_a_reach_in_from_the_public_api(label: str, source: str, expected: list[str]) -> None:
    assert _reach_ins(source) == expected, label


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("autobot-backend/utils/semantic_chunker.py", True),
        ("autobot-backend/utils/semantic_chunker_gpu.py", True),
        ("autobot-backend/utils/semantic_chunker_gpu_test.py", True),
        ("autobot-backend/knowledge/pipeline/extractors/semantic_chunker.py", False),
        ("autobot-backend/npu_semantic_search.py", False),
    ],
)
def test_only_the_chunker_modules_are_exempt(rel: str, expected: bool) -> None:
    assert _is_chunker_module(rel) is expected


@functools.lru_cache(maxsize=1)
def _offenders() -> tuple[tuple[str, ...], int]:
    found, parsed = [], 0
    for rel in REACH.examined(repo_root()):
        if _is_chunker_module(rel):
            continue
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if not any(name in source for name in _PRIVATE):
            continue
        parsed += 1
        if _reach_ins(source):
            found.append(rel)
    return tuple(found), parsed


def test_no_caller_outside_the_chunker_reaches_its_private_hooks() -> None:
    offenders, _ = _offenders()
    assert not offenders, (
        f"#18185: {list(offenders)} call a semantic chunker's private embedding hooks. "
        "Use `load_embedding_model()` / `embed_sentences()` / `embed_sentences_sync()` instead."
    )
