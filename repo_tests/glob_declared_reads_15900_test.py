# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Glob-declared guard inputs, which the concrete-literal checker cannot see (#15900).

`python_filter_covers_its_guards_test.py` records a guard's input only when that
input resolves to a **concrete file**::

    if not (_REPO_ROOT / candidate).is_file():
        return  # a prefix or a glob, not a file this guard reads

So a guard declaring ``".github/workflows/*.yml"`` contributes nothing. Its
dependency is real; its detection is not — and the checker's green therefore
means "no guard reads an uncovered file *by concrete literal*" while its name
claims the general property.

**Why this is a separate record rather than an expansion of that one.** #15900
costed the obvious fix: teaching `_record` to expand globs turns 27 uncovered
entries into roughly 86, because `.github/workflows/` alone holds 64 files.
`MAX_UNCOVERED_READS` only ever goes down, so expansion forces either a 59-entry
cap raise or widening the filter to `.github/workflows/**` — twelve shards on
almost every pull request. That is a CI-spend decision, and it was being made by
an accident of implementation rather than deliberately.

Recording the **declarations** costs none of that. There are 14 of them across 5
guards, against 59+ expansions, and they are the thing a reader needs: *which
guard depends on which tree*. An undetectable dependency and an absent one are
indistinguishable, and this makes them distinguishable without spending a shard.

The population is **discovered** — every quoted repo-relative string containing
`*` — not a list of the four the issue named. That is how the fifth was found:
`scripts/lib/*.sh` is a real uncovered dependency of
`comment_line_number_citations_test.py` that #15900 does not mention.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

#: The record this guard enforces. It lives in its own module because this file
#: reached the 600-line ceiling (#5060); the split is along data/assertions
#: rather than at an arbitrary line, and appends now land in a small data file
#: instead of colliding inside a long test.
from repo_tests._glob_declared_uncovered import GLOB_DECLARED_UNCOVERED
from repo_tests._paths import repo_root
from repo_tests.python_filter_covers_its_guards_test import _filter_patterns, _is_covered

from tools.lint._scan_helpers import tracked_paths

REPO_ROOT = repo_root()

#: A repo-relative path mentioned in a guard, containing a glob. Anchored on a
#: quote for the same reason the sibling checker is: an unquoted match picks up
#: prose and import paths, which are not reads of the tree.
#: The inner class deliberately omits `/`: with it, a separator could be matched
#: either by the literal `/` or inside the class, and the two alternatives
#: multiply. CodeQL measured it as exponential and it is — `"` followed by N
#: repetitions of `*/` took 0.13 ms at N=12 and 573 ms at N=24. Removing the
#: ambiguity makes it linear (0.002 ms at N=30) and matches identically on every
#: real declaration.
_QUOTED_GLOB = re.compile(r"""["']([A-Za-z0-9_.*?\[\]-]+(?:/[A-Za-z0-9_.*?\[\]-]+)*)["']""")


def _is_path_like(candidate: str) -> bool:
    """Whether *candidate* is a repo-relative glob rather than Python syntax.

    Requiring a slash AND `*` missed `"*.toml"`, `"config/?.yml"` and
    `"config/[ab].yml"` (#15994 review). But accepting `?` and `[` naively is
    unusable: brackets are subscripts and type annotations, and a widened regex
    reported `list[Path]`, `os.environ[`, `[Unit]`, `string[]` and
    `github-actions[bot]` as guard dependencies — 44 "uncovered" entries of
    which most were Python source.

    So: a slash means the first segment must be a real directory; without one,
    the string must look like a suffix glob (`*.yml`, `?.min.js`). A bracket
    class is accepted only inside a path that already has a slash.
    """
    if not any(ch in candidate for ch in "*?["):
        return False
    if "[" in candidate and "/" not in candidate and not _SUFFIX_GLOB.match(candidate):
        return False
    if "/" in candidate:
        # `..` and `.` are not repo-relative (#15998 review). `"../*.py"` passed
        # because `REPO_ROOT / ".."` IS a directory — the check answered "does
        # this resolve to something" when the question was "is this a path
        # inside this repository". A traversal component is checked BEFORE the
        # directory test, because the directory test cannot distinguish them.
        #
        # A LEADING slash is the same defect with an empty first segment:
        # `"/actions/runs?"` split to `""`, and `REPO_ROOT / ""` is the root, so
        # `.is_dir()` said yes and URL fragments entered the population.
        head = candidate.split("/", 1)[0]
        if head in ("", ".", ".."):
            return False
        if any(part in {".", ".."} for part in candidate.split("/")):
            return False
        return (REPO_ROOT / head).is_dir()
    return bool(_SUFFIX_GLOB.match(candidate))


#: `*.yml`, `?.min.js`, `*requirements*.txt` — a leading glob and a dotted suffix.
_SUFFIX_GLOB = re.compile(r"^[*?][A-Za-z0-9_.*-]*[.][A-Za-z0-9]+$")


#: Floor on guards PARSED, not on declarations found. A findings floor is
#: satisfied by finding nothing, which is also what a collapsed sweep reports.
_MIN_GUARDS_PARSED = 180


def glob_declarations_in(source: str) -> set[str]:
    """Repo-relative glob declarations mentioned in *source*."""
    # Parsed, not grepped (#15998 review). A regex over raw source counts a glob
    # mentioned INSIDE a string literal — `source = 'for p in ROOT.rglob("*.sh")'`
    # is test data, not a read of the tree — and counts one mentioned in prose.
    # That is exactly the blindness #16011 enumerates, in the guard that found it.
    #
    # A declaration is a string CONSTANT that IS the path, so the whole value is
    # tested rather than a substring of it. A constant containing a newline or a
    # quote is source-as-data or prose, never a pathspec.
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        value = node.value
        if "\n" in value or '"' in value or "'" in value:
            continue
        if _is_path_like(value):
            found.add(value)
    return found


def _probe_path(glob: str) -> str:
    """A concrete path the *glob* would match, for the filter's own matcher."""
    return glob.replace("**/", "").replace("**", "x").replace("*", "x")


def _declared() -> tuple[dict[str, set[str]], int]:
    """Every glob declaration in `repo_tests`, and the number of guards parsed."""
    declarations: dict[str, set[str]] = {}
    parsed = 0
    for rel in tracked_paths(REPO_ROOT, "repo_tests/*.py"):
        # THIS module is excluded, and for the opposite reason to #15990's census.
        # There the guard counted invocations, so skipping itself hid a real
        # bypass. Here the record's own KEYS are quoted glob strings, so scanning
        # this file rediscovers every entry from the record itself — and
        # `test_the_record_only_shrinks` could then never fire, because an entry
        # stays "declared" after its dependent guard stops declaring it. A record
        # that reads itself cannot go stale, which is the same as not checking.
        if Path(rel).name == Path(__file__).name:
            continue
        try:
            source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        parsed += 1
        for glob in glob_declarations_in(source):
            declarations.setdefault(glob, set()).add(rel)
    return declarations, parsed


def test_every_uncovered_glob_declaration_is_recorded() -> None:
    """A glob into a tree the filter misses must be written down, not silent."""
    declarations, parsed = _declared()
    assert parsed >= _MIN_GUARDS_PARSED, (
        f"the sweep parsed {parsed} guards, below the floor of {_MIN_GUARDS_PARSED} — "
        "a shrunken population reports 'no uncovered globs' for the same reason a covered tree does"
    )
    patterns = _filter_patterns()
    uncovered = {g for g in declarations if not _is_covered(_probe_path(g), patterns)}

    unrecorded = sorted(uncovered - set(GLOB_DECLARED_UNCOVERED))
    assert not unrecorded, (
        "these guards declare a glob into a tree the python filter does not cover, and the "
        "dependency is recorded nowhere — so the guard silently does not run when that tree "
        "changes (#15900):\n  " + "\n  ".join(f"{g}  <- {', '.join(sorted(declarations[g]))}" for g in unrecorded)
    )


def test_the_record_only_shrinks() -> None:
    """A resolved entry must be deleted, so the record cannot rot into a wish list."""
    declarations, _ = _declared()
    patterns = _filter_patterns()
    uncovered = {g for g in declarations if not _is_covered(_probe_path(g), patterns)}

    stale = sorted(set(GLOB_DECLARED_UNCOVERED) - uncovered)
    assert not stale, (
        "these entries are no longer uncovered — the filter reaches them now, or the guard "
        "stopped declaring them. Delete them from GLOB_DECLARED_UNCOVERED:\n  " + "\n  ".join(stale)
    )


def test_the_record_names_exactly_the_guards_that_declare_each_glob() -> None:
    """Bidirectional, because a name that is merely plausible is not evidence.

    The first version asserted only that the reason string contained
    `_test.py`, so an entry could name an unrelated guard and pass (#15994
    review) — a record that is wrong in a way nothing detects is worse than one
    that is absent, because a maintainer deciding how to cover the dependency
    trusts it.

    Guards are structured data now, and both directions are checked: every guard
    discovered for a glob must be recorded, and every recorded guard must still
    declare it.
    """
    declarations, _ = _declared()
    for glob, (recorded, _reason) in GLOB_DECLARED_UNCOVERED.items():
        discovered = declarations.get(glob, set())
        assert discovered, f"{glob}: recorded, but no guard declares it any more — delete the entry"
        assert recorded == discovered, (
            f"{glob}: the record names {sorted(recorded)} but the guards declaring it are "
            f"{sorted(discovered)}. Recorded-but-not-declaring: {sorted(recorded - discovered)}; "
            f"declaring-but-not-recorded: {sorted(discovered - recorded)}"
        )


def test_every_record_entry_carries_a_reason() -> None:
    """A reason recording only that a decision happened is not a reason."""
    for glob, (_guards, reason) in GLOB_DECLARED_UNCOVERED.items():
        assert len(reason) > 25, f"{glob}: reason too thin to act on — {reason!r}"


def test_the_detector_reports_a_glob_declaration() -> None:
    """Positive control: the shape this guard exists to see."""
    assert glob_declarations_in('paths = (".github/workflows/*.yml",)') == {".github/workflows/*.yml"}


@pytest.mark.parametrize(
    "source",
    [
        'x = "a concrete/file.yml"',
        'x = "not_a_path"',
        'x = "no-such-tree-here/*.yml"',
    ],
    ids=["concrete-file", "bare-word", "unknown-tree"],
)
def test_the_detector_ignores_what_is_not_a_glob_into_this_tree(source: str) -> None:
    """The contrasts. Without them, "detect globs" is satisfied by reporting every string.

    A concrete literal is the SIBLING checker's job and must not be duplicated
    here; a bare word is not a path; a path into a directory this repository does
    not have is prose, not a read.
    """
    assert glob_declarations_in(source) == set()


@pytest.mark.parametrize(
    "declaration",
    ['x = "*.toml"', 'x = "scripts/?.sh"', 'x = ".github/workflows/*.yml"', 'x = "*requirements*.txt"'],
    ids=["root-suffix", "question-mark", "path-with-star", "embedded-star"],
)
def test_the_detector_accepts_every_supported_glob_form(declaration: str) -> None:
    """Root-relative and `?`-bearing forms, which the first version required a slash and `*` for.

    The review's illustrative `"config/?.yml"` is replaced by `"scripts/?.sh"`:
    a path whose first segment is not a real directory is prose, not a read, and
    this repository has no `config/`. Using it would have asserted the detector
    accepts a shape it correctly rejects.
    """
    assert glob_declarations_in(declaration), f"missed: {declaration}"


@pytest.mark.parametrize(
    "source",
    [
        "x: list[Path] = []",
        'x = os.environ["HOME"]',
        'x = "[Unit]"',
        'x = "string[]"',
        'x = "github-actions[bot]"',
        'x = "[A-Za-z_][A-Za-z0-9_]*"',
    ],
    ids=["annotation", "subscript", "ini-section", "ts-type", "bot-name", "regex"],
)
def test_the_detector_rejects_python_syntax_that_merely_contains_brackets(source: str) -> None:
    """The reason `?` and `[` could not simply be added to the character class.

    A naive widening reported all six of these as guard dependencies — 44
    "uncovered" entries, mostly Python source. Brackets are subscripts and type
    annotations far more often than they are pathspecs.
    """
    assert glob_declarations_in(source) == set()


def test_the_record_cannot_rediscover_itself() -> None:
    """This module is outside its own sweep, so its keys are not declarations.

    Without the exclusion, every entry stays discovered forever — the record
    reads its own keys back and `test_the_record_only_shrinks` can never fire.
    A record that cannot go stale is not being checked.
    """
    declarations, _ = _declared()
    own = {g for g, guards in declarations.items() if any(Path(__file__).name in x for x in guards)}
    assert not own, f"this module's own strings entered the population: {sorted(own)}"


@pytest.mark.parametrize(
    "source",
    ['x = "../*.py"', 'x = "./*.py"', 'x = "scripts/../../*.py"'],
    ids=["parent", "current", "traversal-after-a-real-dir"],
)
def test_the_detector_rejects_paths_that_leave_the_repository(source: str) -> None:
    """`REPO_ROOT / ".."` is a directory, so the `is_dir()` test accepted it (#15998).

    The check answered "does this resolve to something" when the question was
    "is this a path inside this repository" — and the third case shows why the
    component scan cannot be limited to the first segment.
    """
    assert glob_declarations_in(source) == set()


def test_the_declaration_pattern_does_not_backtrack_exponentially() -> None:
    """CodeQL flagged `_QUOTED_GLOB` as exponential, and it was (#15998 review).

    A separator could be matched by the literal `/` or by a class that also
    contained `/`, and the alternatives multiply. Measured before the fix: 0.13 ms
    at 12 repetitions of `*/`, 573 ms at 24 — roughly x4 per two repetitions.

    Asserted as a TIME BUDGET rather than by inspecting the pattern, because the
    property is about matching behaviour and a future edit could reintroduce the
    ambiguity with different characters. Generous enough not to flake on a loaded
    runner; the failing case took half a second at N=24 and would take minutes at
    the N used here.
    """
    import time

    # N=26, not larger. The ambiguous pattern takes ~2.3s here and fails this
    # assertion cleanly; at N=40 it never returns and the mutation HANGS the
    # suite instead of failing it. A test that hangs is worse than one that
    # fails — it reports nothing and blocks the runner.
    pathological = '"' + "*/" * 26 + "!"
    started = time.perf_counter()
    _QUOTED_GLOB.search(pathological)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"the declaration pattern took {elapsed:.1f}s on a pathological input"


def test_the_pattern_still_matches_every_declaration_form() -> None:
    """The contrast: a pattern that matches nothing also cannot backtrack.

    Without this, "fixed the ReDoS" is satisfied by breaking the detector, and
    the record would silently stop discovering anything.
    """
    for source, expected in (
        ('x = "*.toml"', {"*.toml"}),
        ('x = ".github/workflows/*.yml"', {".github/workflows/*.yml"}),
        ('x = "scripts/?.sh"', {"scripts/?.sh"}),
        ('x = "*requirements*.txt"', {"*requirements*.txt"}),
    ):
        assert glob_declarations_in(source) == expected, source


def test_a_glob_inside_a_string_literal_is_not_a_declaration() -> None:
    """Test data is not a read of the tree (#15998 review).

    `repo_root_walks_use_git_15955_test.py` builds fixtures like
    `source = 'for p in ROOT.rglob("*.sh"): pass'`. A regex over raw source
    counted that `"*.sh"` as a declaration and demanded a record entry for a
    dependency that does not exist — which the record's own header forbids
    satisfying by adding one.

    This is #16011's blindness in the guard that enumerates it, and the fix is
    the same: parse, do not grep.
    """
    source = "fixture = 'for p in ROOT.rglob(\"*.sh\"):\\n    pass\\n'\n"
    assert glob_declarations_in(source) == set()


def test_a_glob_in_prose_is_not_a_declaration() -> None:
    """A docstring naming a pattern is documentation, not a dependency."""
    source = '"""This guard sweeps .github/workflows/*.yml and scripts/lib/*.sh."""\n'
    assert glob_declarations_in(source) == set()


def test_a_real_declaration_beside_a_string_fixture_is_still_found() -> None:
    """The contrast. Without it, "ignore strings" is satisfied by ignoring everything.

    A file may hold both — a fixture mentioning a glob and a real pathspec
    argument — and only the second is a read of the tree.
    """
    source = 'fixture = \'ROOT.rglob("*.sh")\'\nnames = tracked_paths(ROOT, "*.j2")\n'
    assert glob_declarations_in(source) == {"*.j2"}


@pytest.mark.parametrize(
    "source",
    ['x = "/actions/runs?"', 'x = "/pulls?"', 'x = "/*.py"'],
    ids=["url-fragment", "url-fragment-2", "leading-slash"],
)
def test_an_absolute_or_url_fragment_is_not_a_declaration(source: str) -> None:
    """A leading slash split to an EMPTY first segment, and `REPO_ROOT / ""` is the root.

    So `.is_dir()` said yes and URL fragments entered the population — the same
    shape as `".."` resolving to the parent, one character shorter.
    """
    assert glob_declarations_in(source) == set()
