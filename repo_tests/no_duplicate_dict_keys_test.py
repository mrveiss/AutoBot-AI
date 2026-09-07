# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No dict literal repeats a key (#15908).

Python takes last-wins silently. A repeated key is not a syntax error, not a
lint finding here, and not visible to black, isort, flake8 or the type checker —
the earlier value is discarded and nothing says so.

The case that prompted this: editing `MODEL_PRICING_PER_1M_TOKENS` I introduced
the same two models twice. The copies happened to agree, so nothing was wrong.
**Had they not agreed, the effective price would have been whichever appeared
last** — a live cost-accounting bug with no failure mode, in a table where a
reader finding the first entry would read the wrong number.

Both duplicates found on the first run of this guard are the same shape and
neither is a pricing table: a summary count assigned, then overwritten by a
detail list under the same key.

**The keys are compared as source text, not as values.** `ast.unparse` renders
`ANTHROPIC_CLAUDE_SONNET4_6` and `"claude-sonnet-4-6"` differently even when the
constant holds that string, so this catches the constant-keyed form the pricing
table uses and the literal-keyed form everything else uses. It does not attempt
to resolve constants: two *different* names holding one value are not a
duplicate key, they are a duplicate value, which is a different question.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Backstop only. Bound to dict literals *parsed*, never to duplicates found: a
#: floor that tracked findings would relax itself as the tree improved, and this
#: population should trend to zero (#15762).
#:
#: A global floor is a weak reach check here, because the population is not
#: evenly spread: `autobot-backend` holds 82% of the literals, so at 20_000 the
#: only sweep failure this caught was losing that one tree. Dropping
#: `autobot_shared` -- where the pricing table that prompted #15908 lives --
#: still cleared it by 16_000. The per-tree assertion below is the real reach
#: check; this catches a partial collapse *within* a tree, which per-tree
#: coverage cannot see.
#:
#: Not pinned to equality, unlike the #15896 floors. Those populations are
#: stable, so equality costs nothing and detects drift in both directions. This
#: one moves with almost every commit; pinning it would churn. The question that
#: separates the two is whether normal work moves the number.
_MIN_DICTS_PARSED = 36_000

#: Files that repeat a key deliberately. Empty, and it should stay that way —
#: an entry here is a dict whose earlier value is known-dead. Recorded by path
#: with a reason if one is ever genuinely needed.
_ALLOWED: frozenset[str] = frozenset()

Duplicate = Tuple[str, int, str]


def _tracked_python_files() -> List[str]:
    completed = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return [name for name in completed.stdout.split("\n") if name and not name.startswith(".worktrees/")]


def duplicate_keys_in(source: str) -> List[Tuple[int, str]]:
    """``(line_no, key_source)`` for every repeated key in a dict literal.

    Keys are compared by their source text. ``**spread`` entries have a ``None``
    key and are skipped — two spreads in one literal are not a duplicate key.
    """
    found: List[Tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        seen: set[str] = set()
        for key in node.keys:
            if key is None:
                continue
            rendered = ast.unparse(key)
            if rendered in seen:
                found.append((getattr(key, "lineno", node.lineno), rendered))
            seen.add(rendered)
    return found


#: Never descended into when discovering trees: not source, or another
#: checkout's copy of this one.
_PRUNED = frozenset({".git", ".worktrees", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"})


def _tree_of(name: str) -> str:
    """The top-level directory a tracked path sits in, or ``<root>``."""
    head, _, tail = name.partition("/")
    return head if tail else "<root>"


def _trees_holding_python() -> Set[str]:
    """Top-level directories containing a ``.py`` file, read off the filesystem.

    Deliberately *not* derived from :func:`_tracked_python_files`. A denominator
    taken from the same source as the numerator cannot detect the numerator
    going missing: the first version of this check counted trees from the swept
    file list, so dropping a tree from that list dropped it from both sides and
    the assertion passed. Same failure as a floor bound to findings instead of
    to reach, one level up.
    """
    trees: Set[str] = set()
    for entry in REPO_ROOT.iterdir():
        if entry.name in _PRUNED:
            continue
        if entry.is_file():
            if entry.suffix == ".py":
                trees.add("<root>")
            continue
        for dirpath, dirnames, filenames in os.walk(entry):
            dirnames[:] = [d for d in dirnames if d not in _PRUNED]
            if any(f.endswith(".py") for f in filenames):
                trees.add(entry.name)
                break
    return trees


def _sweep() -> Tuple[List[Duplicate], int, int, Dict[str, int]]:
    """``(duplicates, files_parsed, dicts_parsed, parsed_per_tree)``."""
    duplicates: List[Duplicate] = []
    files_parsed = dicts_parsed = 0
    parsed_per_tree: Dict[str, int] = {}
    for name in _tracked_python_files():
        path = REPO_ROOT / name
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        files_parsed += 1
        parsed_per_tree[_tree_of(name)] = parsed_per_tree.get(_tree_of(name), 0) + 1
        dicts_parsed += sum(1 for n in ast.walk(tree) if isinstance(n, ast.Dict))
        if name in _ALLOWED:
            continue
        for lineno, key in duplicate_keys_in(path.read_text(encoding="utf-8")):
            duplicates.append((name, lineno, key))
    return duplicates, files_parsed, dicts_parsed, parsed_per_tree


_DUPLICATES, _FILES_PARSED, _DICTS_PARSED, _PARSED_PER_TREE = _sweep()
_TREES_HOLDING_PYTHON = _trees_holding_python()


def test_the_sweep_parsed_a_plausible_number_of_dicts() -> None:
    """Runs first: an empty population passes the assertion below vacuously.

    Bound to dict literals parsed, not to duplicates found. Reported on success
    as well as failure, so a pass reading `0 dicts` is legible as broken rather
    than clean.
    """
    assert _DICTS_PARSED >= _MIN_DICTS_PARSED, (
        f"parsed only {_DICTS_PARSED} dict literal(s) across {_FILES_PARSED} file(s), "
        f"floor is {_MIN_DICTS_PARSED}. FIX THE SWEEP — a clean result below this "
        "floor asserts nothing."
    )


def test_every_tree_holding_python_was_actually_swept() -> None:
    """The reach check the global floor cannot perform.

    Discovery-based on purpose: a tree added tomorrow is covered without anyone
    remembering to add a constant, and losing a tree fails regardless of how few
    literals it held. The global floor only ever noticed the loss of
    `autobot-backend`, which holds 82% of the literals; dropping every other
    tree still cleared it.

    The tree list is read off the filesystem rather than off the swept file
    list, because the two must be able to disagree — see
    :func:`_trees_holding_python`.

    A tree whose every file fails to parse also lands here, and that is the
    intended reading: unparsed is unswept, and a tree this guard cannot read is
    a tree it is not guarding. A tree holding only untracked `.py` files lands
    here too, which is the same statement — this guard sweeps tracked files.
    """
    unswept = sorted(tree for tree in _TREES_HOLDING_PYTHON if _PARSED_PER_TREE.get(tree, 0) == 0)
    assert not unswept, (
        f"tracked Python files exist under {unswept} but the sweep parsed none of them. "
        f"Swept {_FILES_PARSED} file(s) across {len(_PARSED_PER_TREE)} tree(s). "
        "FIX THE SWEEP — a clean result says nothing about an unswept tree."
    )


def test_no_dict_literal_repeats_a_key() -> None:
    assert not _DUPLICATES, (
        f"dict literals with a repeated key ({_DICTS_PARSED} literals swept):\n"
        + "\n".join(f"  {name}:{line}  {key}" for name, line, key in _DUPLICATES)
        + "\n\nPython takes last-wins silently: the earlier value is discarded and "
        "nothing reports it. In a pricing or config table that is a wrong value with "
        "no failure mode (#15908)."
    )


def test_the_detector_reports_a_literal_keyed_duplicate() -> None:
    """The fixture that SHOULD trip it."""
    assert duplicate_keys_in('d = {"a": 1, "b": 2, "a": 3}\n') == [(1, "'a'")]


def test_the_detector_reports_a_constant_keyed_duplicate() -> None:
    """The form the pricing table uses — keys are `Name` nodes, not literals.

    A text scan for a quoted key finds nothing here, which is why this compares
    unparsed source rather than literal values.
    """
    assert duplicate_keys_in("d = {NAME_A: 1, NAME_B: 2, NAME_A: 3}\n") == [(1, "NAME_A")]


def test_the_detector_passes_a_clean_dict() -> None:
    """The contrast case. Without it, a detector returning `[]` for every input
    satisfies every assertion above."""
    assert duplicate_keys_in('d = {"a": 1, "b": 2}\ne = {NAME_A: 1, NAME_B: 2}\n') == []


def test_two_spreads_in_one_literal_are_not_a_duplicate() -> None:
    """`**a, **b` both have a `None` key and are not repeated keys."""
    assert duplicate_keys_in("d = {**a, **b}\n") == []


def test_the_same_key_in_two_separate_dicts_is_not_a_duplicate() -> None:
    """Scoped per literal. Without this the detector would flag every codebase
    that uses a common key name twice, which is all of them."""
    assert duplicate_keys_in('a = {"k": 1}\nb = {"k": 2}\n') == []
