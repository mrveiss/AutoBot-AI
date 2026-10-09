#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18093 AC 5 — regex literals compared by CONCEPT, not by name or by text.

The duplication guard counts identical clones, so six forked regex concepts scored zero
clone lines. `check_symbol_forks.py` matches symbol NAMES, so two patterns for one
concept under different names never cluster. Neither could see any of this.

Grouping by concept is not a tidier version of the same check — it found a live defect
before this guard was even written. The two endpoint normalisers sat side by side only
once sorted by concept: one is a list named `_DYNAMIC_SEGMENT_PATTERNS`, the other two
inline `re.sub` calls, and the second ran its numeric substitution first so a uuid in a
path was never collapsed at all (fixed in `autobot_shared/endpoint_normalization.py`).

What this guard CANNOT see, stated rather than implied:

* Patterns built with an f-string. `autobot_shared/git_refs.py` composes its rule from
  `REF_CHARS`, so it is an `ast.JoinedStr` and no literal sweep reaches it. That is why
  there is no `git-revision` concept below: a guard that reported "0 found" for it would
  be reporting on its own blindness. `autobot_shared/git_refs_test.py` covers that
  concept by behaviour instead.
* Patterns held in a constant and passed to `re` indirectly.
* Anything outside Python — the frontend's TypeScript has its own copies.

So a clean run here means "no LITERAL fork of these three concepts", which is narrower
than "no fork".
"""

from __future__ import annotations

import ast
import functools
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

#: `re` entry points whose first positional argument is a pattern.
_RE_FUNCS = frozenset({"compile", "match", "search", "sub", "fullmatch", "findall", "split", "subn"})


class Concept:
    """One regex concept: how to recognise it, and where it is allowed to live."""

    def __init__(self, name: str, recognizer: str, canonical: dict[str, str], allowed: dict[str, str]):
        self.name = name
        self.recognizer = re.compile(recognizer)
        self.canonical = canonical
        self.allowed = allowed

    @property
    def permitted(self) -> set[str]:
        return set(self.canonical) | set(self.allowed)


CONCEPTS = (
    Concept(
        "ansi-escape",
        r"\\x1[bB]|\\033",
        canonical={
            "autobot-backend/utils/encoding_utils.py": (
                "owns the six ESC-introduced patterns; `strip_ansi_escapes` is the safe "
                "entry point and `strip_ansi_codes` composes it for raw terminal output"
            )
        },
        allowed={
            "pipeline-scripts/check_gating_precommit_hooks.py": ("standalone CI tool; cannot import the backend"),
            "scripts/duplication_gate.py": "standalone CI tool; cannot import the backend",
        },
    ),
    Concept(
        "frontmatter-fence",
        r"^\^?-{3}(?:\[| |\\s|\\r|\\n|\$)",
        canonical={
            "autobot_shared/frontmatter.py": ("the one parser; replaced four incompatible variants across seven sites")
        },
        allowed={
            "autobot-backend/chat_workflow/models.py": (
                "NOT front matter: matches a `---`-delimited CRITICAL MULTI-STEP block " "inside a prompt template"
            ),
            "autobot-backend/code_intelligence/doc_generation/markdown_generator.py": (
                "NOT front matter: `_MD_HR_RE`, a horizontal rule, beside `_MD_H1_RE`, "
                "`_MD_BOLD_RE` and `_MD_LIST_ITEM_RE`"
            ),
        },
    ),
    Concept(
        "uuid",
        r"\[0-9a-f\]\{8\}-\[0-9a-f\]\{4\}",
        canonical={
            "autobot-backend/utils/validators.py": "validates a uuid; anchored, used by `validate_uuid`",
            "autobot_shared/endpoint_normalization.py": (
                "COLLAPSES a uuid inside a path to a placeholder; unanchored on purpose, "
                "a different concept from validating one"
            ),
        },
        allowed={},
    ),
)


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(repo_root()),
        env=scrubbed_git_env(),
        check=True,
    )
    return tuple(line for line in result.stdout.splitlines() if line and "__pycache__" not in line)


def _is_test(rel: str) -> bool:
    return rel.endswith("_test.py") or "/tests/" in rel or rel.rsplit("/", 1)[-1].startswith("test_")


@functools.lru_cache(maxsize=1)
def _regex_literals() -> tuple[tuple[str, int, str], tuple[int, ...]]:
    """Every `re.<func>("literal", ...)` in non-test Python, plus a parse census.

    The census is returned so a test can assert the sweep actually read the tree -- an
    empty result and a tree it could not parse look identical otherwise.
    """
    root = repo_root()
    found: list[tuple[str, int, str]] = []
    parsed = 0
    skipped = 0
    for rel in _tracked_python_files():
        try:
            tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            skipped += 1
            continue
        parsed += 1
        if _is_test(rel):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in _RE_FUNCS):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "re"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.append((rel, node.lineno, first.value))
    return tuple(found), (parsed, skipped)


def test_the_sweep_actually_read_the_tree() -> None:
    """An empty sweep satisfies every assertion below by looking at nothing."""
    literals, (parsed, skipped) = _regex_literals()
    assert parsed > 3000, f"only {parsed} files parsed"
    assert skipped < 20, f"{skipped} files failed to parse — the sweep is partly blind"
    assert len(literals) > 300, f"only {len(literals)} regex literals found"


@pytest.mark.parametrize("concept", CONCEPTS, ids=lambda c: c.name)
def test_each_concept_recognises_its_own_canonical(concept: Concept) -> None:
    """A recognizer that matches nothing would pass the fork test vacuously."""
    literals, _ = _regex_literals()
    matched = {rel for rel, _, pat in literals if concept.recognizer.search(pat)}
    missing = set(concept.canonical) - matched
    assert not missing, (
        f"#18093: the {concept.name} recognizer no longer matches its canonical "
        f"{sorted(missing)} — the recognizer is broken, not the tree, and the fork test "
        "below would pass while seeing nothing."
    )


@pytest.mark.parametrize("concept", CONCEPTS, ids=lambda c: c.name)
def test_no_new_fork_of_a_consolidated_concept(concept: Concept) -> None:
    literals, _ = _regex_literals()
    offenders = sorted(
        f"{rel}:{lineno}"
        for rel, lineno, pat in literals
        if concept.recognizer.search(pat) and rel not in concept.permitted
    )
    assert not offenders, (
        f"#18093: a new {concept.name} pattern was written outside its canonical home: "
        f"{offenders}. Canonical: {sorted(concept.canonical)}. If this is a genuinely "
        "different concept, add it to that concept's `allowed` with the reason — "
        "`_MD_HR_RE` is the example of a real one."
    )


@pytest.mark.parametrize("concept", CONCEPTS, ids=lambda c: c.name)
def test_every_allowlist_entry_still_matches_the_concept(concept: Concept) -> None:
    """An entry stranded by a refactor exempts a path nobody is using any more."""
    literals, _ = _regex_literals()
    matched = {rel for rel, _, pat in literals if concept.recognizer.search(pat)}
    stale = sorted(set(concept.allowed) - matched)
    assert not stale, (
        f"#18093: {concept.name} allowlist entries no longer hold a pattern of that "
        f"concept: {stale}. Remove them — an exemption whose subject is gone silently "
        "widens the guard."
    )


@pytest.mark.parametrize("concept", CONCEPTS, ids=lambda c: c.name)
def test_every_permitted_path_exists(concept: Concept) -> None:
    tracked = set(_tracked_python_files())
    missing = sorted(p for p in concept.permitted if p not in tracked)
    assert not missing, f"#18093: {concept.name} names paths that are not tracked files: {missing}"


def test_the_blind_spots_are_recorded() -> None:
    """`git_refs.py` is deliberately absent, and this asserts why.

    Its pattern is an f-string over `REF_CHARS`, so it is an `ast.JoinedStr` and no
    literal sweep can see it. Adding a `git-revision` concept here would report "0
    found" about the guard's own blindness rather than about the tree. If that pattern
    ever becomes a plain literal, this test fails and the concept should be added.
    """
    source = (repo_root() / "autobot_shared/git_refs.py").read_text(encoding="utf-8")
    assert 'rf"' in source or 'f"' in source, "git_refs.py no longer composes its pattern — add the concept"
    literals, _ = _regex_literals()
    from_git_refs = [pat for rel, _, pat in literals if rel == "autobot_shared/git_refs.py"]
    assert not any("A-Za-z0-9" in pat for pat in from_git_refs), (
        "git_refs.py now holds a literal revision pattern — a `git-revision` concept "
        "can and should be added to CONCEPTS."
    )
