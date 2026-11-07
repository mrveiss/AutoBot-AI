# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the #15900 glob detector counts as a declared read, pinned case by case.

Split out of ``glob_declared_reads_15900_test.py`` at its 600-line ceiling (#5060) when the
dotless named-file form (#19575) and the pathspec filter (#18800) added cases. That module holds
the record checks; this one holds the detector's contrasts and its time budgets. Its quoted
fixtures are test data, so the sweep skips this file (``_SELF_AND_ITS_RECORD``).
"""

from __future__ import annotations

import pytest
from repo_tests.glob_declared_reads_15900_test import _NAMED_GLOB, _QUOTED_GLOB, _is_path_like, glob_declarations_in


@pytest.mark.parametrize(
    "declaration",
    [
        'x = "*.toml"',
        'x = "scripts/?.sh"',
        'x = ".github/workflows/*.yml"',
        'x = "*requirements*.txt"',
        'x = "*Dockerfile*"',
        'x = "Dockerfile*"',
        'x = "*Containerfile"',
        'x = "Makefile*"',
        'x = "*Jenkinsfile"',
    ],
    ids=[
        "root-suffix",
        "question-mark",
        "path-with-star",
        "embedded-star",
        "dotless-both",
        "dotless-tail",
        "dotless-head",
        "makefile",
        "jenkinsfile",
    ],
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


@pytest.mark.parametrize(
    "source",
    ['x = "*"', 'x = "note*"', 'x = "*Dockerfiles are great"', 'x = "Docker*"'],
    ids=["bare-star", "prose-word", "prose-after-name", "partial-name"],
)
def test_a_dotless_glob_counts_only_over_a_known_file_name(source: str) -> None:
    """The decision for dotless globs (#19575): only a known extensionless name makes one a read.

    A bare `*` is every file, not a declared read. A word with a star is prose. The name must be
    whole: `Docker*` does not name the Dockerfile.
    """
    assert glob_declarations_in(source) == set()


@pytest.mark.parametrize(
    "source",
    [
        'x = "Use the autobot-* scale; status colours map to --color-error/-success/-warning."',
        'x = "' + "scripts/" + "a" * 300 + '*.py"',
        'x = """docs/*.md\nscripts/*.sh"""',
    ],
    ids=["prose-with-star-and-slash", "over-long-component", "multi-line"],
)
def test_a_string_that_is_not_a_pathspec_never_reaches_the_filesystem(source: str) -> None:
    """Prose and over-long strings are rejected before `is_dir()`, so they cannot raise (#18800).

    The first case is the shape of the `raw_palette_class_ratchet_14580_test` message that raised
    ENAMETOOLONG on Python 3.10; the second is longer than any path component may be.
    """
    assert glob_declarations_in(source) == set()


@pytest.mark.parametrize(
    "candidate",
    ["docs/*.md\nscripts/*.sh", "scripts/x *.py", "a" * 300 + "/x*.py"],
    ids=["newline", "space", "over-long-head"],
)
def test_the_pathspec_filter_alone_stops_a_candidate_before_the_filesystem(candidate: str) -> None:
    """Called below `_QUOTED_GLOB`, which excludes spaces and newlines by itself (#18800).

    Without the filter the newline and space cases are accepted, because `docs` and `scripts` are
    real directories, and the over-long head reaches `is_dir()`, which raises ENAMETOOLONG on 3.10.
    """
    assert not _is_path_like(candidate)


def test_the_named_glob_pattern_stays_linear() -> None:
    """Same time budget as `_QUOTED_GLOB`: a pathological dotless input must not backtrack (#15998)."""
    import time

    started = time.perf_counter()
    _NAMED_GLOB.match("*Dockerfile" + "*-" * 5000 + "!")
    assert time.perf_counter() - started < 1.0


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
        ('x = "*Dockerfile*"', {"*Dockerfile*"}),
    ):
        assert glob_declarations_in(source) == expected, source
