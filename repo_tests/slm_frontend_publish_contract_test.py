# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both SLM publishers satisfy the same contract, and disagreement is the failure (#15724).

The two existing guards each assert the contract in their own words and both
pass. What nothing checked was whether they still describe the *same* contract.
This does: every clause is evaluated against every implementation, so a clause
satisfied on one side and not the other is a failure naming both.
"""

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest
from repo_tests.slm_frontend_publish_contract import (
    CLAUSES,
    IMPLEMENTATIONS,
    MIN_IMPLEMENTATIONS,
    REPO_ROOT,
)

#: What makes a file a *publisher* is that it flips the served pointer, not that
#: it builds. `npm run build:slm` alone is a builder: `role_registry.py` and
#: `role.json.j2` both run it, and neither publishes -- vite's default `outDir`
#: is `dist`, a sibling of the served `current` symlink, so they produce a
#: bundle nothing serves (#15889). Keying the search on the build command
#: reported those as unregistered publishers, which they are not.
#:
#: The search runs over the tree rather than over the registry, or it could only
#: ever find what it already knew about.
_PUBLISHER_HINTS = (
    re.compile(r"mv -T \.current\.next current"),
    # The Python spelling. Without it this search could only find publishers
    # written in a shell dialect -- which is how `services/slm_frontend_build.py`
    # sat unregistered while the guard reported a complete registry. A detector
    # that recognises one language cannot find a third-language implementation,
    # which is the exact case #15724 asks it to catch.
    re.compile(r"os\.replace\(staged, root / link_name\)"),
)

#: A `build:slm` invocation that does not pass `--outDir` builds into vite's
#: default `dist`. That is not an outage today, because `dist` is a sibling of
#: `current` rather than `current` itself -- but it is one config change away
#: from being one, which is why these are enumerated rather than ignored.
_UNSTAGED_BUILDERS = {
    "autobot-slm-backend/services/role_registry.py": "#15889 -- post_sync_cmd builds into dist/, which nothing serves",
    "autobot-slm-backend/ansible/roles/slm_manager/templates/role.json.j2": "#15889 -- build_steps, same shape",
}

#: Files that legitimately mention the idiom without being publishers: the
#: contract itself, the guards, and documentation. Listed by path with the
#: reason, rather than inferred from context.
#: Only files that actually contain the flip idiom need to be here. Each entry
#: was checked: the two guards that merely mention publishing were removed
#: again, because an allowlist entry that is not load-bearing is a standing
#: exemption for whatever later takes that path.
_NOT_PUBLISHERS = {
    "repo_tests/slm_frontend_publish_contract.py",
    "repo_tests/slm_frontend_publish_contract_test.py",
    "repo_tests/slm_frontend_atomic_publish_15610_test.py",
}


def strip_comments(text: str) -> str:
    """Drop whole-line comments before matching.

    Both implementations document the flip idiom in prose directly above the
    code that performs it -- the Ansible file carries
    `#     && mv -T .current.next current` at line 82 and the real task at 212.
    Matching raw text means a clause is satisfied by the explanation of the
    behaviour rather than the behaviour, so deleting the task and keeping the
    comment passes. Found by mutation: weakening the real task left every test
    green.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _sources() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, path in IMPLEMENTATIONS.items():
        assert path.is_file(), f"the {name} publisher is missing or moved: {path}"
        out[name] = strip_comments(path.read_text(encoding="utf-8"))
    return out


def clause_violations(sources: Dict[str, str]) -> List[Tuple[str, str, List[str]]]:
    """(clause, why, implementations failing it) for every clause not met everywhere."""
    out = []
    for clause in CLAUSES:
        failing = [impl for impl, text in sources.items() if not re.search(clause.patterns[impl], text)]
        if failing:
            out.append((clause.name, clause.why, failing))
    return out


def test_the_sweep_reached_both_implementations() -> None:
    """Runs first: an empty registry passes every assertion below vacuously.

    Bound to implementations discovered, never to violations found.
    """
    assert (
        len(IMPLEMENTATIONS) >= MIN_IMPLEMENTATIONS
    ), f"only {len(IMPLEMENTATIONS)} publishers registered, floor is {MIN_IMPLEMENTATIONS}"
    for name, path in IMPLEMENTATIONS.items():
        assert path.is_file(), f"the {name} publisher is missing or moved: {path}"
        assert path.stat().st_size > 0, f"the {name} publisher is empty"


def test_every_clause_holds_in_every_implementation() -> None:
    violations = clause_violations(_sources())

    assert not violations, "the two SLM publishers no longer agree:\n" + "\n".join(
        f"  [{name}] not satisfied by: {', '.join(failing)}\n      {why}" for name, why, failing in violations
    )


@pytest.mark.parametrize("clause", CLAUSES, ids=lambda c: c.name)
def test_each_clause_is_stated_for_every_implementation(clause) -> None:
    """A clause missing a pattern for one side would silently exempt it.

    `clause_violations` only checks implementations the clause names, so an
    absent key is not a failure there -- it is an exemption nobody declared.
    """
    missing = set(IMPLEMENTATIONS) - set(clause.patterns)
    assert not missing, (
        f"clause {clause.name!r} states no pattern for {sorted(missing)}, so that "
        "implementation is exempt from it without anyone saying so"
    )


def test_no_unlisted_publisher_exists() -> None:
    """A third implementation in a third language is caught, not accommodated."""
    registered = {str(p.relative_to(REPO_ROOT)) for p in IMPLEMENTATIONS.values()}
    unlisted: List[str] = []

    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".sh", ".yml", ".yaml", ".j2", ".py"}:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        if rel.startswith((".git/", ".worktrees/")) or "/node_modules/" in f"/{rel}":
            continue
        if rel in registered or rel in _NOT_PUBLISHERS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(h.search(text) for h in _PUBLISHER_HINTS):
            unlisted.append(rel)

    assert not unlisted, (
        "these look like SLM frontend publishers but are not registered in "
        "IMPLEMENTATIONS, so no clause is checked against them:\n  "
        + "\n  ".join(sorted(unlisted))
        + "\n\nRegister them, or add them to _NOT_PUBLISHERS with the reason."
    )
