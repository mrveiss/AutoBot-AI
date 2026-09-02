# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The oracle three guards trust must read every manifest, not most of them (#15518).

``declared_distributions.py`` answers "is this distribution declared?" for
``embedded_python_dependency_declared_test.py``,
``hard_optional_dependency_declared_test.py`` and
``infra_script_imports_resolve_test.py``. While it globbed only
``requirements*.txt`` it read 20 of the 32 tracked manifests and missed 13
distributions declared exclusively under ``requirements-ci/``, and each caller's
``>= 15`` floor passed on the 24 files it did read.

The floors here measure the shape of the input rather than its size alone: a
count can be met by the wrong files, so the directory-shaped manifests are
asserted for by name.
"""

from __future__ import annotations

import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

from repo_tests.declared_distributions import (
    MANIFEST_PATTERNS,
    SKIP_PARTS,
    _globbed,
    _manifests,
    declared_distributions,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_manifests() -> set[str]:
    """Repository-relative paths of every tracked requirements manifest."""
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "-C", str(_REPO_ROOT), "ls-files", "-z", "--", "*requirements*.txt"],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    return {
        rel
        for rel in out.split("\0")
        if rel and not any(part in SKIP_PARTS for part in Path(rel).parts)
    }


def test_the_oracle_reads_every_tracked_manifest() -> None:
    """The #15518 defect: manifests that are not *named* ``requirements*`` went unread."""
    tracked = _tracked_manifests()
    assert len(tracked) >= 30, (
        f"git reports only {len(tracked)} tracked manifests — FIX THE SWEEP, "
        "this comparison has nothing to compare against"
    )
    read = {str(p.relative_to(_REPO_ROOT)) for p in _manifests(_REPO_ROOT)}
    missed = sorted(tracked - read)
    assert not missed, (
        "these manifests are tracked but the declaration oracle never reads "
        "them, so every distribution declared only there reads as declared "
        "nowhere and becomes a false finding in three guards (#15518):\n  "
        + "\n  ".join(missed)
    )


def test_the_directory_shaped_manifests_are_actually_reached() -> None:
    """A file count can be met by the wrong files; name the shape that was missing."""
    read = {str(p.relative_to(_REPO_ROOT)) for p in _manifests(_REPO_ROOT)}
    nested = sorted(rel for rel in read if "/" in rel and not Path(rel).name.startswith("requirements"))
    assert nested, (
        "the oracle read no manifest living inside a requirements* directory — "
        "FIX THE SWEEP, that is exactly the population #15518 was filed about"
    )
    assert "requirements*/*.txt" in MANIFEST_PATTERNS, "the widening pattern is gone"


def test_the_declaration_floors_hold() -> None:
    """Population floors. An oracle that reads nothing declares nothing.

    That is the dangerous direction: an empty declaration set turns *every*
    third-party import in three guards into a reported finding.
    """
    names, files = declared_distributions(_REPO_ROOT)
    assert files >= 30, (
        f"only read {files} manifests, floor 30 (37 measured) — FIX THE SWEEP, "
        "the oracle has gone blind"
    )
    assert len(names) >= 180, (
        f"only {len(names)} distributions declared, floor 180 (197 measured) — "
        "FIX THE SWEEP, the line parser no longer matches what manifests emit"
    )


def test_the_parser_still_matches_what_a_manifest_emits(tmp_path: Path) -> None:
    """Positive control: comments, pins, extras and quoting all parse as intended."""
    manifest = tmp_path / "requirements-ci"
    manifest.mkdir()
    (manifest / "control.txt").write_text(
        "# a comment\n\nSome-Dist>=1.2.3\n'quoted-dist'==2.0\nplain_dist\n",
        encoding="utf-8",
    )
    names, files = declared_distributions(tmp_path)
    assert files == 1, f"expected the nested manifest to be read, read {files}"
    assert {"some_dist", "quoted_dist", "plain_dist"} <= names, f"parsed {sorted(names)}"


#: Distributions declared in exactly ONE place, a ``requirements-ci/`` manifest
#: the pre-#15518 filename glob could not open. Each read as "declared nowhere"
#: before the widening, which is the false finding this guard exists to prevent.
CI_ONLY_DISTRIBUTIONS = ("pygetwindow", "langchain_text_splitters", "mouseinfo")


def test_a_distribution_declared_only_under_requirements_ci_reads_as_declared() -> None:
    """The #15518 acceptance criterion, asserted on named distributions.

    A count can be met by the wrong files, and "197 declared" would still pass
    if these three were missing. Naming them is what makes the criterion
    checkable: each is declared in exactly one ``requirements-ci/`` file, so
    each reads as declared only if that file was actually opened.
    """
    names, _ = declared_distributions(_REPO_ROOT)
    missing = [d for d in CI_ONLY_DISTRIBUTIONS if d not in names]
    assert not missing, (
        f"{missing} are declared only under requirements-ci/ and the oracle "
        "does not see them — every import of one would be reported as an "
        "undeclared dependency by three guards (#15518)"
    )


def test_a_manifest_reachable_only_through_an_include_line_is_read() -> None:
    """``constraints/shared.txt`` matches no filename pattern; only ``-c`` reaches it.

    The filename widening alone leaves this file unread, so a population that
    is merely *wider* is still not complete. The include closure is what closes
    it, and this names the file that proves the closure runs.
    """
    read = {str(p.relative_to(_REPO_ROOT)) for p in _manifests(_REPO_ROOT)}
    globbed = {str(p.relative_to(_REPO_ROOT)) for p in _globbed(_REPO_ROOT)}
    reached_only_by_include = read - globbed
    assert reached_only_by_include, (
        "the include closure contributed no manifest at all — FIX THE SWEEP, "
        "a file pulled in with -r/-c and matching no filename pattern would go unread"
    )
    assert "constraints/shared.txt" in reached_only_by_include, (
        "constraints/shared.txt is pulled in by an include line and matches no "
        f"filename pattern, but the closure reached {sorted(reached_only_by_include)}"
    )
