# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The python-suite path filter must reach every tree its guards read (#15713).

`.github/filters/python-paths.yml` decides whether the twelve-shard Python
suite runs. A `repo_tests` guard that reads a NON-Python tree -- ansible roles,
Dockerfiles, shell scripts, service templates -- is only as good as that
filter: if the filter omits the tree, a change confined to it computes
``python != 'true'``, the required-context shim reports ``python-suite`` green,
and the guard written to catch that change never runs.

This has now happened three times. #14544 added five deployment sources after
one slipped; #14891 added the hook and infrastructure trees after sixteen hooks
sat outside their guard; #15704 changed ansible role defaults only, took the
shim's green, merged, and left ``Dev_new_gui`` red on all twelve shards.

Each fix added the specific paths that had just broken. This asserts the
general property instead: every top-level tree a guard reads is covered.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest

from repo_tests.python_filter_uncovered_reads import MAX_UNCOVERED_READS, UNCOVERED_READS

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FILTER = _REPO_ROOT / ".github" / "filters" / "python-paths.yml"
_GUARD_DIR = _REPO_ROOT / "repo_tests"

#: A repo-relative path mentioned in a guard's source. Deliberately anchored on
#: a quote: an unquoted match picks up prose and import paths, which are not
#: reads of the tree.
_QUOTED_PATH = re.compile(r"""["']([a-z0-9_.-]+/[A-Za-z0-9_./*-]+)["']""")

#: The same read written segment by segment: `_REPO_ROOT / "tree" / "file.yml"`.
#: Fifty-two guards build their subjects this way, and none of those literals
#: contains a slash -- so a detector keyed on the quoted form alone reports a
#: tree as unread while a guard reads it every run, which is the reach failure
#: this whole guard exists to prevent, committed by the guard itself.
_COMPOSED_PATH = re.compile(r"""_REPO_ROOT\s*((?:/\s*["'][A-Za-z0-9_.*-]+["']\s*)+)""")
_SEGMENT = re.compile(r"""["']([A-Za-z0-9_.*-]+)["']""")

#: Trees whose contents no guard reads directly, so the filter need not name
#: them even when a path string mentions one.
_NOT_A_READ = frozenset({"repo_tests", "pipeline-scripts", "scripts", "tools", "libs"})

#: Floor on the sweep's REACH. Bound to guards parsed, never to findings: a
#: floor on findings passes when the walk reads nothing, and then fixing a real
#: gap trips it. Both directions are wrong and one of them is silent.
_MIN_GUARDS_READ = 60


def _filter_patterns() -> list[str]:
    document = yaml.safe_load(_FILTER.read_text(encoding="utf-8"))
    assert isinstance(document, dict) and "python" in document, f"{_FILTER} lost its `python` key"
    return [str(pattern) for pattern in document["python"]]


def _is_covered(path: str, patterns: list[str]) -> bool:
    """Whether the filter runs the suite for a change to *path*.

    `**/*.py` covers every Python file wherever it lives, which is why a tree
    full of modules is not at risk merely because a guard names one. The gap is
    the NON-Python input: a role default, a Dockerfile, a service template, a
    shell script. Those are covered only if a pattern names the file or its
    tree explicitly.
    """
    if path.endswith(".py"):
        return True
    for pattern in patterns:
        if pattern == path:
            return True
        head, sep, tail = pattern.partition("/**")
        if sep and (path == head or path.startswith(f"{head}/")):
            return True
        if fnmatch.fnmatch(path, pattern.replace("**/", "*/").replace("**", "*")):
            return True
    return False


def _record(candidate: str, guard: str, patterns: list[str], reads: dict[str, set[str]]) -> None:
    """Note *candidate* as an uncovered read, if it is one."""
    tree = candidate.split("/", 1)[0]
    if tree in _NOT_A_READ or not (_REPO_ROOT / tree).is_dir():
        return
    if not (_REPO_ROOT / candidate).is_file():
        return  # a prefix or a glob, not a file this guard reads
    if _is_covered(candidate, patterns):
        return
    reads.setdefault(candidate, set()).add(guard)


def _uncovered_reads(patterns: list[str]) -> tuple[dict[str, set[str]], int]:
    """`uncovered path -> guards reading it`, and how many guards were parsed."""
    reads: dict[str, set[str]] = {}
    parsed = 0
    for path in sorted(_GUARD_DIR.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        parsed += 1
        composed = (
            "/".join(_SEGMENT.findall(match.group(1)))
            for match in _COMPOSED_PATH.finditer(source)
        )
        for candidate in (m.group(1) for m in _QUOTED_PATH.finditer(source)):
            _record(candidate, path.name, patterns, reads)
        for candidate in composed:
            _record(candidate, path.name, patterns, reads)
    return reads, parsed


def test_the_sweep_reaches_the_guards_it_claims_to() -> None:
    """Reach before findings -- an empty walk must fail, not pass silently."""
    _, parsed = _uncovered_reads(_filter_patterns())
    assert parsed >= _MIN_GUARDS_READ, (
        f"the walk parsed only {parsed} guards (floor {_MIN_GUARDS_READ}) — it has stopped reading"
    )


def test_python_filter_covers_every_tree_a_guard_reads() -> None:
    """The property the three prior one-off fixes each approximated."""
    uncovered, _ = _uncovered_reads(_filter_patterns())
    new = {path: guards for path, guards in uncovered.items() if path not in UNCOVERED_READS}

    assert not new, (
        "these trees are read by repo_tests guards but the python-suite filter does not "
        "cover them, so a change confined to one takes the required-context shim's green "
        "while the guard never runs:\n  "
        + "\n  ".join(f"{path} — read by {sorted(guards)[0]}" for path, guards in sorted(new.items()))
    )


def test_the_uncovered_record_only_shrinks() -> None:
    """A drained entry must be removed, and the ceiling lowered with it.

    Shrink-only fails in BOTH directions on purpose. An entry left behind after
    the filter grew to cover it reads as a live bypass that is not one, and the
    next person spends the same afternoon re-deriving why.
    """
    uncovered, _ = _uncovered_reads(_filter_patterns())
    assert len(uncovered) == MAX_UNCOVERED_READS, (
        f"{len(uncovered)} uncovered guard inputs, but MAX_UNCOVERED_READS says "
        f"{MAX_UNCOVERED_READS}. Equality, not a bound: headroom under a ceiling is "
        "room for a new bypass to appear with nothing failing. Widening the filter "
        "means removing the entry AND lowering this number in the same commit."
    )

    stale = sorted(path for path in UNCOVERED_READS if path not in uncovered)
    assert not stale, (
        "the filter now covers these, so they are no longer bypasses — remove them from "
        "UNCOVERED_READS and lower MAX_UNCOVERED_READS to match:\n  " + "\n  ".join(stale)
    )


#: Contrast fixtures: an input the filter reaches and a near miss that it does
#: not, so a classifier that answered True (or False) for everything fails here
#: instead of passing silently over the real tree.
COVERAGE_CONTRASTS = (
    # Explicitly named in the filter.
    (".github/workflows/ci.yml", True),
    # Any Python file, anywhere, via `**/*.py`.
    ("autobot-backend/main.py", True),
    # #15713 widened the filter to this tree; a role default is covered now.
    ("autobot-slm-backend/ansible/roles/backend/defaults/main.yml", True),
    # A workflow the filter does NOT name -- the shape the record exists for.
    (".github/workflows/code-quality.yml", False),
    # A generated frontend type a guard compares against.
    ("autobot-slm-frontend/openapi.json", False),
)


@pytest.mark.parametrize(("path", "expected"), COVERAGE_CONTRASTS)
def test_coverage_classifier_discriminates(path: str, expected: bool) -> None:
    assert _is_covered(path, _filter_patterns()) is expected, path


def test_composed_paths_are_detected_not_only_quoted_ones(tmp_path: Path) -> None:
    """A guard that builds its subject segment by segment must still be seen.

    `_REPO_ROOT / "tree" / "file.yml"` contains no literal with a slash in it,
    so a detector keyed on the quoted form alone reports the tree as unread
    while a guard reads it every run. Fifty-two guards here build paths this
    way -- a reach failure inside the guard that exists to prevent reach
    failures.
    """
    guard = tmp_path / "sample_test.py"
    guard.write_text(
        'A = _REPO_ROOT / "docker" / "with-secrets.sh"\n'
        'B = "docker/secrets-init.sh"\n',
        encoding="utf-8",
    )
    composed = ["/".join(_SEGMENT.findall(m.group(1))) for m in _COMPOSED_PATH.finditer(guard.read_text(encoding="utf-8"))]
    quoted = [m.group(1) for m in _QUOTED_PATH.finditer(guard.read_text(encoding="utf-8"))]

    assert composed == ["docker/with-secrets.sh"], composed
    assert "docker/secrets-init.sh" in quoted


def test_a_composed_path_with_no_repo_root_base_is_ignored() -> None:
    """The contrast: only a `_REPO_ROOT`-anchored chain is a repository read."""
    assert not _COMPOSED_PATH.findall('X = somewhere / "docker" / "with-secrets.sh"')
