# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the file-size hook's exclusions hide, counted and ratcheted (#15897).

`check_python_file_size.EXCLUDED_PREFIXES` removes three trees from the size
sweep. `.worktrees/` is right — those are not repository files. The other two,
`autobot-infrastructure/` and `autobot-backend/code_analysis/`, are tracked
source, and **47 files in them exceed the 600-line ceiling with no entry in
`KNOWN_LARGE`** — the largest at 2,341 lines, 3.9x the limit.

That is #15897's thesis exactly: the baseline records exemptions, and these are
exemptions the enumeration never offered it. Not because anyone decided they
should be exempt, but because the walk never saw them to ask.

**Why this counts them rather than grandfathering them.** Adding 47 entries to
`KNOWN_LARGE` would reverse two rulings this file has no standing to overturn:

* that mapping's own docstring says *"THIS MAPPING ONLY SHRINKS. Never add an
  entry to make a new file pass; split the file instead."*
* `EXCLUDED_PREFIXES` is mirrored in `.pre-commit-config.yaml` and pinned by
  `test_excluded_prefixes_mirror_the_pre_commit_config`, so narrowing it widens
  the pre-commit hook for every committer in the same commit — a scope decision,
  not a visibility one.

A grandfathered ceiling and an unscanned tree are also different things, and
conflating them would lose that. So the debt gets its own number, in its own
place, and the number only shrinks. **An exemption you can read is a decision;
this is what makes these readable without pretending they were decided.**
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from repo_tests._reach import declare
from tools.lint._scan_helpers import tracked_paths

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOK = _REPO_ROOT / "scripts" / "check_python_file_size.py"

#: Trees excluded from the size sweep that ARE repository source. `.worktrees/`
#: is deliberately absent: it holds other checkouts, not this one's files.
_SOURCE_TREES = ("autobot-infrastructure/", "autobot-backend/code_analysis/")

#: Files in those trees over the ceiling, today. **Only ever lower this.**
#: Equality, not a bound: headroom here is room for a new oversized file to
#: appear in an unscanned tree with nothing failing, which is the exact
#: condition that produced the 47.
#:
#: Lower it by splitting a file, or by bringing its tree into
#: `EXCLUDED_PREFIXES`' scope — which is a decision for whoever also updates
#: `.pre-commit-config.yaml`, not something to do incidentally here.
EXCLUDED_TREE_DEBT = 47


def _hook():
    spec = importlib.util.spec_from_file_location("_size_hook", _HOOK)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _source_tree_files(root: Path) -> list[str]:
    """Tracked `.py` files in the excluded trees that are real repo source.

    Enumerated through `tracked_paths` (#15926) rather than the hook's own
    `tracked_python_files`, which applies `EXCLUDED_PREFIXES` and would return
    exactly the empty set this exists to look inside.
    """
    return [rel for rel in tracked_paths(root, "*.py") if rel.startswith(_SOURCE_TREES)]


REACH = declare(
    "excluded-tree-size-debt",
    discover=_source_tree_files,
    floor=300,
    what="tracked python files in excluded source trees",
    growth=100,
)


def _line_count(path: Path) -> int:
    with path.open(encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def test_the_excluded_trees_were_actually_walked() -> None:
    """Positive assertion first: an empty walk makes the count below vacuous."""
    REACH.examined(_REPO_ROOT)


def test_the_size_debt_hidden_by_exclusions_only_shrinks() -> None:
    """The 47 are invisible to the ratchet; this is what makes them countable.

    Bound to the count, not to a per-file ceiling. A per-file mapping would be
    `KNOWN_LARGE` again, and these files are not grandfathered — they are
    unscanned, which is a different claim.
    """
    hook = _hook()
    over = sorted(
        (
            (rel, _line_count(_REPO_ROOT / rel))
            for rel in _source_tree_files(_REPO_ROOT)
        ),
        key=lambda pair: -pair[1],
    )
    offenders = [(rel, n) for rel, n in over if n > hook.MAX_LINES]

    assert len(offenders) == EXCLUDED_TREE_DEBT, (
        f"{len(offenders)} files in {list(_SOURCE_TREES)} exceed "
        f"{hook.MAX_LINES} lines; EXCLUDED_TREE_DEBT says {EXCLUDED_TREE_DEBT}.\n"
        f"Went UP: a new oversized file landed in a tree the size hook does not "
        f"scan. Split it — the exclusion is why nothing else will tell you.\n"
        f"Went DOWN: lower EXCLUDED_TREE_DEBT to {len(offenders)} in this commit.\n"
        f"Largest: " + ", ".join(f"{rel} ({n})" for rel, n in offenders[:3])
    )
